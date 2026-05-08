"""転写モジュール — faster-whisper ラッパー。プラットフォーム統一出力を返す。"""

from __future__ import annotations

import gc
import os
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

_BEAM_SIZE = 3
_INTER_CHUNK_SLEEP_SEC = 5


def _get_cpu_threads() -> int:
    """CPU スレッド数を返す。ECHONOTE_CPU_THREADS 環境変数でオーバーライド可能。

    デフォルト: 物理コア数 // 2（HT/SMT を除いた実コアの半分）。
    """
    env = os.environ.get("ECHONOTE_CPU_THREADS", "")
    if env.isdigit() and int(env) > 0:
        return int(env)
    physical = psutil.cpu_count(logical=False) or 2
    return max(1, physical // 2)


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


def _split_audio_chunks(
    audio_path: str, chunk_sec: int, tmp_dir: str
) -> list[tuple[str, float]]:
    """ffmpeg でファイルを chunk_sec 秒ごとに WAV 分割する。(chunk_path, offset_sec) のリストを返す。"""
    duration = _get_audio_duration(audio_path)
    if duration <= 0:
        return [(audio_path, 0.0)]
    chunks: list[tuple[str, float]] = []
    start = 0.0
    idx = 0
    while start < duration:
        out_path = os.path.join(tmp_dir, f"chunk_{idx:04d}.wav")
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", audio_path,
                "-ss", str(start),
                "-t", str(chunk_sec),
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                out_path,
            ],
            capture_output=True,
            check=True,
        )
        chunks.append((out_path, start))
        start += chunk_sec
        idx += 1
    return chunks


def _stream_faster_whisper(
    audio_path: str,
    model_size: str,
    language: str,
    device: str = "cpu",
    compute_type: str = "int8",
    on_chunk: Callable[[int, int, float, float], None] | None = None,
    chunk_minutes: int = 5,
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
                for i, (chunk_path, offset_sec) in enumerate(chunks):
                    end_min = min(offset_sec + chunk_minutes * 60, duration) / 60
                    if on_chunk:
                        on_chunk(i, total, offset_sec / 60, end_min)
                    print(
                        f"[transcriber] チャンク {i + 1}/{total}"
                        f"（{offset_sec / 60:.0f}〜{end_min:.0f} 分）処理中",
                        flush=True,
                    )
                    segs, _ = model.transcribe(chunk_path, language=language, beam_size=_BEAM_SIZE)
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
            segments, _ = model.transcribe(audio_path, language=language, beam_size=_BEAM_SIZE)
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
):
    """音声ファイルを転写し、セグメントを順次 yield する。

    on_chunk(idx, total, start_min, end_min): チャンク処理開始時に呼ばれるコールバック。
    chunk_minutes: チャンク分割の長さ（分）。この長さを超える音声を自動分割する。
    """
    _check_ffmpeg()
    audio_path = str(audio_path)

    use_mlx = (
        sys.platform == "darwin"
        and (settings is None or settings.platform.value == "mac")
    )

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

    yield from _stream_faster_whisper(audio_path, model_size, language, on_chunk=on_chunk, chunk_minutes=chunk_minutes)


def transcribe(
    audio_path: str | Path,
    model_size: str,
    language: str,
    settings: Settings | None = None,
) -> list[Segment]:
    """音声ファイルを転写して [{start, end, text}] を返す。"""
    return list(transcribe_stream(audio_path, model_size, language, settings))
