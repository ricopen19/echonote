"""転写モジュール — faster-whisper / Moonshine ラッパー。プラットフォーム統一出力を返す。"""

from __future__ import annotations

import gc
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import psutil

if TYPE_CHECKING:
    from echonote.config import Settings

Segment = dict  # {"start": float, "end": float, "text": str}

WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v2", "large-v3", "large-v3-turbo"]

_SAMPLE_RATE = 16_000
_CHUNK_SECONDS = 30
_mlx_model_cache: dict = {}

_BEAM_SIZE_BY_TIER = {"light": 1, "standard": 3, "performance": 5}
_BEAM_SIZE_DEFAULT = 3
_INTER_CHUNK_SLEEP_SEC = 5

# Moonshine
_MOONSHINE_MODEL_REPO = "csukuangfj2/sherpa-onnx-moonshine-base-ja-quantized-2026-02-27"
_MOONSHINE_MODEL_DIR = Path.home() / ".cache" / "echonote" / "moonshine-base-ja"
_SILERO_VAD_REPO = "R4kSo1997/sherpa-onnx-silero-vad-v5"
_SILERO_VAD_PATH = Path.home() / ".cache" / "echonote" / "silero_vad.onnx"
_moonshine_cache: dict = {}  # recognizer のシングルトンキャッシュ

# Windows: システム環境の古い ORT DLL が sherpa-onnx に混入するのを防ぐため
# venv の onnxruntime capi を PE ローダーの検索パスに明示的に追加する。
if sys.platform == "win32":
    try:
        import onnxruntime as _ort
        os.add_dll_directory(str(Path(_ort.__file__).parent / "capi"))
        del _ort
    except Exception:
        pass


def _get_cpu_threads() -> int:
    """CPU スレッド数を返す。ECHONOTE_CPU_THREADS 環境変数でオーバーライド可能。

    デフォルト: 物理コア数 // 2（HT/SMT を除いた実コアの半分）。
    """
    env = os.environ.get("ECHONOTE_CPU_THREADS", "")
    if env.isdigit() and int(env) > 0:
        return int(env)
    physical = psutil.cpu_count(logical=False) or 2
    return max(1, physical // 2)


def _clean_jp(text: str) -> str:
    """sherpa-onnx がトークン間に挿入するスペースを除去して自然な日本語に整形する。

    ASCII英数字の前後はスペースを保持し、日本語文字間のスペースのみ除去する。
    """
    tokens = text.split()
    if not tokens:
        return ""
    buf = [tokens[0]]
    for tok in tokens[1:]:
        prev = buf[-1]
        if not prev[-1].isascii() and not tok[0].isascii():
            buf[-1] += tok
        else:
            buf.append(" " + tok)
    return "".join(buf).strip()


def _remove_repetitions(text: str) -> str:
    """Moonshine の幻覚による繰り返しフレーズを除去する。

    連続する同一パターン（2文字以上）を1回に圧縮する。
    「バラバラバラ」→「バラ」、「そうか。そうか。そうか。」→「そうか。」
    """
    if not text:
        return text

    # 1文字の大量繰り返し（5回以上）を2回に圧縮: "あああああ" → "ああ"
    text = re.sub(r"(.)\1{4,}", r"\1\1", text)

    # 2文字以上のパターンの連続繰り返しを除去（最大30回試行）
    for _ in range(30):
        m = re.search(r"(.{2,}?)\1+", text)
        if m:
            text = text[: m.start()] + m.group(1) + text[m.end() :]
        else:
            break

    return text.strip()


def _ensure_moonshine_assets() -> tuple[Path, Path]:
    """Moonshine モデルと Silero VAD モデルを返す。未DLなら自動ダウンロード。"""
    from huggingface_hub import hf_hub_download, snapshot_download

    _MOONSHINE_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    _SILERO_VAD_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not (_MOONSHINE_MODEL_DIR / "encoder_model.ort").exists():
        print(f"[transcriber] Moonshine モデルをダウンロード中（初回のみ）...", flush=True)
        snapshot_download(repo_id=_MOONSHINE_MODEL_REPO, local_dir=str(_MOONSHINE_MODEL_DIR))

    if not _SILERO_VAD_PATH.exists():
        print("[transcriber] Silero VAD モデルをダウンロード中（初回のみ）...", flush=True)
        hf_hub_download(
            repo_id=_SILERO_VAD_REPO,
            filename="silero_vad.onnx",
            local_dir=str(_SILERO_VAD_PATH.parent),
        )

    return _MOONSHINE_MODEL_DIR, _SILERO_VAD_PATH


def _get_moonshine_recognizer():
    """Moonshine recognizer をシングルトンとして返す。"""
    import sherpa_onnx
    if "recognizer" not in _moonshine_cache:
        model_dir, _ = _ensure_moonshine_assets()
        _moonshine_cache["recognizer"] = sherpa_onnx.OfflineRecognizer.from_moonshine_v2(
            encoder=str(model_dir / "encoder_model.ort"),
            decoder=str(model_dir / "decoder_model_merged.ort"),
            tokens=str(model_dir / "tokens.txt"),
            num_threads=_get_cpu_threads(),
            provider="cpu",
        )
    return _moonshine_cache["recognizer"]


def _stream_moonshine(
    audio_path: str,
    on_chunk: Callable[[int, int, float, float], None] | None = None,
):
    """Moonshine + Silero VAD で音声を転写し、セグメントを順次 yield する。"""
    import numpy as np
    import sherpa_onnx
    import wave

    _SR = 16_000
    _VAD_WINDOW = 512  # Silero VAD の処理単位
    # ONNX量子化モデルは約10秒超でエラーになるため7.5秒でハードクリップする
    _MAX_SAMPLES = int(7.5 * _SR)

    _, silero_path = _ensure_moonshine_assets()
    recognizer = _get_moonshine_recognizer()

    # 16kHz WAV に変換
    tmp_wav = tempfile.mktemp(suffix=".wav")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path,
             "-ar", str(_SR), "-ac", "1", "-c:a", "pcm_s16le", tmp_wav],
            capture_output=True, check=True,
        )
        with wave.open(tmp_wav) as wf:
            frames = wf.readframes(wf.getnframes())
            audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    finally:
        try:
            os.unlink(tmp_wav)
        except OSError:
            pass

    # Silero VAD で音声区間を検出
    vad_config = sherpa_onnx.VadModelConfig(
        silero_vad=sherpa_onnx.SileroVadModelConfig(
            model=str(silero_path),
            threshold=0.12,
            min_silence_duration=1.2,
            min_speech_duration=0.3,
            max_speech_duration=8.5,
        ),
        sample_rate=_SR,
    )
    vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=60)

    speech_segments: list[tuple[int, np.ndarray]] = []

    def _drain_vad() -> None:
        while not vad.empty():
            seg = vad.front
            speech_segments.append((seg.start, np.array(seg.samples, dtype=np.float32)))
            vad.pop()

    for i in range(0, len(audio), _VAD_WINDOW):
        chunk = audio[i : i + _VAD_WINDOW]
        if len(chunk) < _VAD_WINDOW:
            chunk = np.pad(chunk, (0, _VAD_WINDOW - len(chunk)))
        vad.accept_waveform(chunk)
        _drain_vad()  # バッファ溢れを防ぐため投入ごとにポップ

    vad.flush()  # 末尾セグメントを確定（忘れると消失する）
    _drain_vad()

    # VADが max_speech_duration を超えるセグメントを返す場合があるため
    # アプリ側で _MAX_SAMPLES でハードクリップして分割する
    clipped: list[tuple[int, np.ndarray]] = []
    for start_sample, samples in speech_segments:
        offset = 0
        while offset < len(samples):
            clipped.append((start_sample + offset, samples[offset : offset + _MAX_SAMPLES]))
            offset += _MAX_SAMPLES

    total = len(clipped)
    for idx, (start_sample, samples) in enumerate(clipped):
        start_sec = start_sample / _SR
        end_sec = start_sec + len(samples) / _SR

        if on_chunk:
            on_chunk(idx, total, start_sec / 60, end_sec / 60)

        stream = recognizer.create_stream()
        stream.accept_waveform(_SR, samples)
        recognizer.decode_stream(stream)
        text = _remove_repetitions(_clean_jp(stream.result.text.strip()))

        if text:
            yield {"start": start_sec, "end": end_sec, "text": text}


def _check_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg が見つかりません。インストールしてください。\n"
            "  Windows: https://ffmpeg.org/download.html\n"
            "  Mac: brew install ffmpeg"
        )


def _get_audio_duration(audio_path: str) -> float:
    """ffprobe で音声の長さ（秒）を返す。取得できなければ 0 を返す。"""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _find_silence_split_points(audio_path: str, max_chunk_sec: int) -> list[float]:
    """ffmpeg silencedetect で無音中間点を検出し、max_chunk_sec 以内の分割点を貪欲法で返す。
    無音が検出できない場合は空リストを返す（呼び出し側が時間固定にフォールバック）。
    """
    result = subprocess.run(
        ["ffmpeg", "-i", audio_path, "-af", "silencedetect=noise=-40dB:d=0.3", "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    midpoints = []
    for m in re.finditer(r"silence_end: ([\d.]+) \| silence_duration: ([\d.]+)", result.stderr):
        end, dur = float(m.group(1)), float(m.group(2))
        midpoints.append(end - dur / 2)

    if not midpoints:
        return []

    splits: list[float] = []
    last = 0.0
    while True:
        candidates = [p for p in midpoints if last < p <= last + max_chunk_sec]
        if not candidates:
            break
        last = max(candidates)
        splits.append(last)
    return splits


def _split_audio_chunks(
    audio_path: str, chunk_sec: int, tmp_dir: str
) -> list[tuple[str, float]]:
    """音声を無音区間で分割する。無音が検出できない場合は時間固定にフォールバック。
    (chunk_path, offset_sec) のリストを返す。
    """
    duration = _get_audio_duration(audio_path)
    if duration <= 0:
        return [(audio_path, 0.0)]

    split_points = _find_silence_split_points(audio_path, chunk_sec)
    if not split_points:
        # フォールバック: 時間固定分割
        split_points = [s for s in (float(i) * chunk_sec for i in range(1, int(duration / chunk_sec) + 1)) if s < duration]

    boundaries = [0.0, *split_points, duration]
    chunks: list[tuple[str, float]] = []
    for idx, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
        out_path = os.path.join(tmp_dir, f"chunk_{idx:04d}.wav")
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", audio_path,
                "-ss", str(start),
                "-t", str(end - start),
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                out_path,
            ],
            capture_output=True,
            check=True,
        )
        chunks.append((out_path, start))
    return chunks


def _stream_faster_whisper(
    audio_path: str,
    model_size: str,
    language: str,
    device: str = "cpu",
    compute_type: str = "int8",
    on_chunk: Callable[[int, int, float, float], None] | None = None,
    chunk_minutes: int = 5,
    beam_size: int = _BEAM_SIZE_DEFAULT,
):
    from faster_whisper import WhisperModel

    duration = _get_audio_duration(audio_path)
    use_chunks = duration > chunk_minutes * 60

    model = WhisperModel(model_size, device=device, compute_type=compute_type, cpu_threads=_get_cpu_threads())
    try:
        if use_chunks:
            with tempfile.TemporaryDirectory() as tmp_dir:
                chunks = _split_audio_chunks(audio_path, chunk_minutes * 60, tmp_dir)
                total = len(chunks)
                # 各チャンクの終端時刻: 次チャンクの開始 or 音声全体の長さ
                ends = [chunks[j + 1][1] for j in range(len(chunks) - 1)] + [duration]
                for i, ((chunk_path, offset_sec), end_sec) in enumerate(zip(chunks, ends)):
                    if on_chunk:
                        on_chunk(i, total, offset_sec / 60, end_sec / 60)
                    print(
                        f"[transcriber] チャンク {i + 1}/{total}"
                        f"（{offset_sec / 60:.0f}〜{end_sec / 60:.0f} 分）処理中",
                        flush=True,
                    )
                    segs, _ = model.transcribe(chunk_path, language=language, beam_size=beam_size, vad_filter=True)
                    for s in segs:
                        text = s.text.strip()
                        if text:
                            yield {
                                "start": s.start + offset_sec,
                                "end": s.end + offset_sec,
                                "text": text,
                            }
                    if i < total - 1:
                        print(f"[transcriber] {_INTER_CHUNK_SLEEP_SEC}秒冷却中...", flush=True)
                        time.sleep(_INTER_CHUNK_SLEEP_SEC)
        else:
            if on_chunk:
                on_chunk(0, 1, 0.0, duration / 60)
            segments, _ = model.transcribe(audio_path, language=language, beam_size=beam_size, vad_filter=True)
            for s in segments:
                yield {"start": s.start, "end": s.end, "text": s.text.strip()}
    finally:
        del model
        gc.collect()


def _patch_mlx_model_cache() -> None:
    """mlx-whisper の load_model にモジュールレベルキャッシュを注入する。"""
    try:
        import mlx_whisper.load_models as _lm
    except ImportError:
        return
    if getattr(_lm, "_echonote_patched", False):
        return
    _orig = _lm.load_model
    def _cached(path_or_hf_repo: str):
        if path_or_hf_repo not in _mlx_model_cache:
            _mlx_model_cache[path_or_hf_repo] = _orig(path_or_hf_repo)
        return _mlx_model_cache[path_or_hf_repo]
    _lm.load_model = _cached
    _lm._echonote_patched = True


def _stream_mlx_whisper(
    audio_path: str,
    model_size: str,
    language: str,
):
    import mlx_whisper

    _patch_mlx_model_cache()

    _MODEL_MAP = {
        "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
        "large-v3": "mlx-community/whisper-large-v3",
        "medium": "mlx-community/whisper-medium",
        "small": "mlx-community/whisper-small",
        "base": "mlx-community/whisper-base",
        "tiny": "mlx-community/whisper-tiny",
    }
    repo = _MODEL_MAP.get(model_size, f"mlx-community/whisper-{model_size}")
    lang = language if language != "auto" else None
    chunk_samples = _SAMPLE_RATE * _CHUNK_SECONDS

    audio = mlx_whisper.audio.load_audio(audio_path)
    try:
        offset = 0
        while offset < len(audio):
            chunk = audio[offset : offset + chunk_samples]
            offset_sec = offset / _SAMPLE_RATE
            result = mlx_whisper.transcribe(chunk, path_or_hf_repo=repo, language=lang)
            for s in result.get("segments", []):
                text = s["text"].strip()
                if text:
                    yield {"start": s["start"] + offset_sec, "end": s["end"] + offset_sec, "text": text}
            try:
                import mlx.core as mx
                mx.clear_cache()
            except AttributeError:
                pass
            offset += chunk_samples
    finally:
        _mlx_model_cache.clear()
        gc.collect()


def transcribe_stream(
    audio_path: str | Path,
    model_size: str,
    language: str,
    settings: Settings | None = None,
    on_chunk: Callable[[int, int, float, float], None] | None = None,
    chunk_minutes: int = 5,
    engine: str = "whisper",
):
    """音声ファイルを転写し、セグメントを順次 yield する。

    engine: "whisper"（デフォルト）または "moonshine"。
    on_chunk(idx, total, start_min, end_min): チャンク処理開始時に呼ばれるコールバック。
    chunk_minutes: Whisper 使用時のチャンク分割長（分）。Moonshine 時は VAD が担うため無視。
    """
    _check_ffmpeg()
    audio_path = str(audio_path)

    if engine == "moonshine":
        yield from _stream_moonshine(audio_path, on_chunk=on_chunk)
        return

    use_mlx = (
        sys.platform == "darwin"
        and (settings is None or settings.platform.value == "mac")
    )

    beam_size = _BEAM_SIZE_BY_TIER.get(settings.hw_tier.value, _BEAM_SIZE_DEFAULT) if settings else _BEAM_SIZE_DEFAULT

    if use_mlx:
        try:
            yield from _stream_mlx_whisper(audio_path, model_size, language)
            return
        except ImportError:
            print("[transcriber] mlx-whisper 未インストール → faster-whisper にフォールバック", flush=True)
        except Exception as e:
            # HuggingFace の 404 は既知の問題（モデル名がmlx-community に未登録）→ 静かにフォールバック
            if "RepositoryNotFoundError" in type(e).__name__ or "404" in str(e):
                print(
                    f"[transcriber] mlx-community/whisper-{model_size} が HF に存在しません"
                    " → faster-whisper にフォールバック",
                    flush=True,
                )
            else:
                traceback.print_exc()
                print(f"[transcriber] mlx-whisper 失敗 ({type(e).__name__}) → faster-whisper FB", flush=True)

    yield from _stream_faster_whisper(audio_path, model_size, language, on_chunk=on_chunk, chunk_minutes=chunk_minutes, beam_size=beam_size)


def transcribe(
    audio_path: str | Path,
    model_size: str,
    language: str,
    settings: Settings | None = None,
) -> list[Segment]:
    """音声ファイルを転写して [{start, end, text}] を返す。"""
    return list(transcribe_stream(audio_path, model_size, language, settings))
