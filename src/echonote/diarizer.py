"""話者分離モジュール — resemblyzer（優先）/ pyannote-audio（フォールバック）。"""

from __future__ import annotations

import functools
import gc
import json
import subprocess
import sys
from pathlib import Path
from typing import Literal

DiarizeBackend = Literal["auto", "nemotron"]  # 呼び出し側が選べる方式
UsedBackend = Literal["nemotron", "resemblyzer", "pyannote"]  # 実際に使われた方式

_CLUSTER_THRESHOLD = 0.45  # AgglomerativeClustering の cosine 距離閾値
_MERGE_MIN_SEC = 2.0        # これ未満のセグメントは直前に結合してからembeddingを計算する


KRule = int | Literal["threshold", "silhouette"]  # 話者数の指定 / 距離の閾値 / silhouette 探索
_MIN_SPEAKER_RATIO = 0.03  # 発話時間がこの割合未満の話者は最近傍の話者に統合する


def cluster_speakers(embeddings, durations: list[float], k_rule: KRule) -> list[str]:
    """埋め込み1行につき話者ラベル1つを返す。呼び出し側は len(embeddings) == len(durations) を守る。"""
    import numpy as np
    from sklearn.cluster import AgglomerativeClustering

    arr = np.asarray(embeddings)
    if len(arr) <= 1:
        return ["SPEAKER_00"] * len(arr)

    def fit(**kw) -> list[int]:
        return AgglomerativeClustering(metric="cosine", linkage="average", **kw).fit_predict(arr).tolist()

    if isinstance(k_rule, int):
        labels = fit(n_clusters=min(max(2, k_rule), len(arr)))
    elif k_rule == "threshold":
        labels = fit(n_clusters=None, distance_threshold=_CLUSTER_THRESHOLD)
    else:
        from sklearn.metrics import silhouette_score

        best_k, best_score = 2, -1.0
        for k in range(2, min(12, len(arr) - 1) + 1):
            score = float(silhouette_score(arr, fit(n_clusters=k), metric="cosine"))
            if score > best_score:
                best_score, best_k = score, k
        labels = fit(n_clusters=best_k)

    # 少数話者の統合
    if len(set(labels)) > 1:
        label_times: dict[int, float] = {}
        for lbl, dur in zip(labels, durations):
            label_times[lbl] = label_times.get(lbl, 0.0) + dur
        min_time = sum(label_times.values()) * _MIN_SPEAKER_RATIO
        kept = {lbl for lbl, t in label_times.items() if t >= min_time}
        if kept and len(kept) < len(label_times):  # 全員 3% 未満なら統合しない
            centroids = {lbl: arr[[i for i, l in enumerate(labels) if l == lbl]].mean(axis=0) for lbl in label_times}

            def cos_dist(a, b) -> float:
                return 1.0 - float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))

            remap = {
                lbl: lbl if lbl in kept else min(kept, key=lambda o: cos_dist(centroids[lbl], centroids[o]))
                for lbl in label_times
            }
            labels = [remap[l] for l in labels]

    # 登場順に話者ラベルを振る
    names: dict[int, str] = {}
    for lbl in labels:
        names.setdefault(lbl, f"SPEAKER_{len(names):02d}")
    return [names[l] for l in labels]


def _ensure_pkg_resources() -> None:
    import sys, types
    if "pkg_resources" not in sys.modules:
        _stub = types.ModuleType("pkg_resources")
        _stub.get_distribution = lambda name: type("D", (), {"version": "0.0.0"})()
        sys.modules["pkg_resources"] = _stub


def _load_wav(audio_path: str):
    """16kHz モノラルで読み、音量だけをそろえる。preprocess_wav と違い無音を削らない（区間の時刻を保つため）。"""
    import librosa
    from resemblyzer.audio import normalize_volume

    wav, _ = librosa.load(audio_path, sr=16_000, mono=True)
    return normalize_volume(wav, -30, increase_only=True)


def _embed_segments(wav, sr: int, segs: list[dict], encoder) -> tuple[list, list[int]]:
    embeddings: list = []
    valid_indices: list[int] = []
    for i, seg in enumerate(segs):
        chunk = wav[int(seg["start"] * sr) : int(seg["end"] * sr)]
        if len(chunk) >= int(sr * 0.5):
            embeddings.append(encoder.embed_utterance(chunk))
            valid_indices.append(i)
    return embeddings, valid_indices


def _merge_short_segments(segments: list[dict]) -> tuple[list[dict], list[int]]:
    """2秒未満のセグメントを直前のセグメントに結合する。

    Returns:
        merged: 結合後セグメントリスト
        origin_to_merged: 元インデックス → 結合後インデックスのマッピング
    """
    merged: list[dict] = []
    origin_to_merged: list[int] = []
    for seg in segments:
        dur = seg["end"] - seg["start"]
        if dur < _MERGE_MIN_SEC and merged:
            merged[-1] = {**merged[-1], "end": seg["end"]}
            origin_to_merged.append(len(merged) - 1)
        else:
            origin_to_merged.append(len(merged))
            merged.append({"start": seg["start"], "end": seg["end"]})
    return merged, origin_to_merged


# ── resemblyzer ───────────────────────────────────────────────────────────────

def _diarize_resemblyzer(audio_path: str, segments: list[dict], n_speakers: int | None = None) -> list[dict]:
    _ensure_pkg_resources()
    from resemblyzer import VoiceEncoder
    import numpy as np

    wav = _load_wav(audio_path)
    sr = 16_000
    encoder = VoiceEncoder("cpu")

    merged_segs, origin_to_merged = _merge_short_segments(segments)
    embeddings, valid_merged_indices = _embed_segments(wav, sr, merged_segs, encoder)

    if not embeddings:
        return [{**seg, "speaker": "SPEAKER_00"} for seg in segments]

    arr = np.array(embeddings)
    durations = [merged_segs[i]["end"] - merged_segs[i]["start"] for i in valid_merged_indices]
    speakers = cluster_speakers(arr, durations, n_speakers or "threshold")
    merged_speakers = dict(zip(valid_merged_indices, speakers))

    # 元セグメントへ逆マッピング
    return [
        {**seg, "speaker": merged_speakers.get(origin_to_merged[i], "SPEAKER_00")}
        for i, seg in enumerate(segments)
    ]


# ── pyannote-audio ────────────────────────────────────────────────────────────

def _patch_torch_load() -> None:
    """PyTorch 2.6+ の weights_only=True デフォルト変更を pyannote 向けにパッチ。"""
    try:
        import torch
        if getattr(torch, "_echonote_load_patched", False):
            return
        _orig = torch.load

        @functools.wraps(_orig)
        def _patched(*args, **kwargs):
            kwargs.setdefault("weights_only", False)
            return _orig(*args, **kwargs)

        torch.load = _patched
        torch._echonote_load_patched = True
    except ImportError:
        pass


def _detect_device() -> str:
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


def _assign_turns(turns: list[tuple[float, float, str]], segments: list[dict]) -> list[dict]:
    """話者ターンをセグメントに割り当てる（最大重複の1話者。重ならなければ SPEAKER_00）。"""
    result = []
    for seg in segments:
        seg_start, seg_end = seg["start"], seg["end"]
        best_speaker = "SPEAKER_00"
        best_overlap = 0.0
        for t_start, t_end, speaker in turns:
            overlap = min(seg_end, t_end) - max(seg_start, t_start)
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = speaker
        result.append({**seg, "speaker": best_speaker})
    return result


def _assign_speakers(diarization, segments: list[dict]) -> list[dict]:
    """pyannote の出力から話者区間を取り出してセグメントに割り当てる。"""
    # pyannote 4.x は DiarizeOutput.speaker_diarization、3.x は Annotation を直接返す
    annotation = getattr(
        diarization, "speaker_diarization",
        getattr(diarization, "diarization",
        getattr(diarization, "annotation", diarization)),
    )
    turns = [
        (turn.start, turn.end, speaker)
        for turn, _, speaker in annotation.itertracks(yield_label=True)
    ]
    return _assign_turns(turns, segments)


def _diarize_pyannote(audio_path: str, hf_token: str, segments: list[dict]) -> list[dict]:
    try:
        from pyannote.audio import Pipeline
    except ImportError as e:
        raise ImportError(
            "pyannote-audio が未インストールです。`uv sync --extra diarization` を実行してください。"
        ) from e

    _patch_torch_load()

    import torch

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=hf_token,
    )
    try:
        pipeline.to(torch.device(_detect_device()))
        diarization = pipeline(audio_path)
        return _assign_speakers(diarization, segments)
    finally:
        del pipeline
        gc.collect()


# ── Nemotron 3 Diarization（別 venv + subprocess）────────────────────────────

_NEMOTRON_DIR = Path(__file__).resolve().parents[2] / "experiments" / "nemotron"
_NEMOTRON_TIMEOUT_SEC = 3600
NEMOTRON_AVAILABLE = (_NEMOTRON_DIR / ".venv").is_dir()  # 未セットアップなら UI に出さない


def _diarize_nemotron(audio_path: str, segments: list[dict]) -> list[dict]:
    proc = subprocess.run(
        ["uv", "run", "--project", str(_NEMOTRON_DIR), "python", str(_NEMOTRON_DIR / "run.py"), audio_path],
        capture_output=True, text=True, timeout=_NEMOTRON_TIMEOUT_SEC, check=True,
    )
    turns = [(float(t["start"]), float(t["end"]), str(t["speaker"])) for t in json.loads(proc.stdout)]
    return _assign_turns(turns, segments)


# ── 公開 API ──────────────────────────────────────────────────────────────────

def diarize(
    audio_path: str | Path,
    hf_token: str,
    segments: list[dict],
    n_speakers: int | None = None,
    backend: DiarizeBackend = "auto",
) -> tuple[list[dict], UsedBackend]:
    """話者分離を実行し、speaker キーを付加したセグメントと実際に使った backend 名を返す。

    Args:
        backend: "nemotron" なら Nemotron 3 Diarization を先に試し、失敗時は auto と同じ経路へ
            フォールバックする（n_speakers は無視される）。"auto" は resemblyzer（HF トークン不要）を
            優先し、未インストールなら pyannote-audio（HF トークン必須）を使う。
    """
    audio_path = str(audio_path)

    if backend == "nemotron":
        try:
            return _diarize_nemotron(audio_path, segments), "nemotron"
        except Exception as e:  # venv 無し・非0終了・JSON 不正・タイムアウト → resemblyzer へ
            print(f"[echonote] nemotron 失敗、resemblyzer へフォールバック: {type(e).__name__}: {e}", file=sys.stderr)

    try:
        import resemblyzer  # noqa: F401
        return _diarize_resemblyzer(audio_path, segments, n_speakers=n_speakers), "resemblyzer"
    except ImportError:
        pass

    if not hf_token:
        raise ValueError(
            "HuggingFace トークンが未設定です。設定タブで HF_TOKEN を入力してください。"
        )
    return _diarize_pyannote(audio_path, hf_token, segments), "pyannote"


def _smooth_turns(timeline: list[dict], min_sec: float) -> list[dict]:
    """短い話者ターンを隣接ターンに統合してノイズを除去する。"""
    if min_sec <= 0 or len(timeline) < 2:
        return timeline

    segs = [dict(s) for s in timeline]
    changed = True
    while changed:
        changed = False
        # サンドイッチパターン：前後が同じ話者で囲まれた短いセグメントを統合
        i = 1
        while i < len(segs) - 1:
            dur = segs[i]["end"] - segs[i]["start"]
            if dur < min_sec and segs[i - 1]["speaker"] == segs[i + 1]["speaker"]:
                segs[i - 1]["end"] = segs[i + 1]["end"]
                del segs[i : i + 2]
                changed = True
            else:
                i += 1
        # 端の短いセグメントを隣に統合
        if len(segs) >= 2:
            if segs[0]["end"] - segs[0]["start"] < min_sec:
                segs[1]["start"] = segs[0]["start"]
                segs.pop(0)
                changed = True
            elif segs[-1]["end"] - segs[-1]["start"] < min_sec:
                segs[-2]["end"] = segs[-1]["end"]
                segs.pop(-1)
                changed = True

    # 連続する同一話者をまとめる
    result: list[dict] = []
    for seg in segs:
        if result and result[-1]["speaker"] == seg["speaker"]:
            result[-1]["end"] = seg["end"]
        else:
            result.append(seg)
    return result


def diarize_standalone(
    audio_path: str | Path,
    n_speakers: int | None = None,
    min_turn_sec: float = 2.0,
) -> list[dict]:
    """Whisperなしで話者タイムラインを生成する。

    Args:
        audio_path: 音声ファイルパス
        n_speakers: 話者数（None で自動検出）
        min_turn_sec: この秒数未満の話者ターンをスムージングで除去する

    Returns:
        [{"start": float, "end": float, "speaker": str}, ...]
    """
    _ensure_pkg_resources()
    import numpy as np
    import webrtcvad
    from resemblyzer import VoiceEncoder

    audio_path = str(audio_path)
    wav = _load_wav(audio_path)
    sr = 16_000
    duration = len(wav) / sr

    # VAD でセグメント検出
    vad = webrtcvad.Vad(2)
    frame_ms = 30
    frame_samples = int(sr * frame_ms / 1000)
    pcm16 = (wav * 32767).astype(np.int16).tobytes()

    raw_segs: list[dict] = []
    seg_start: float | None = None
    for i in range(0, len(wav) - frame_samples, frame_samples):
        frame = pcm16[i * 2 : (i + frame_samples) * 2]
        is_speech = vad.is_speech(frame, sr)
        t = i / sr
        if is_speech and seg_start is None:
            seg_start = t
        elif not is_speech and seg_start is not None:
            if t - seg_start >= 0.5:
                raw_segs.append({"start": seg_start, "end": t})
            seg_start = None
    if seg_start is not None:
        raw_segs.append({"start": seg_start, "end": duration})

    if not raw_segs:
        return [{"start": 0.0, "end": duration, "speaker": "SPEAKER_00"}]

    encoder = VoiceEncoder("cpu")
    embeddings, valid_indices = _embed_segments(wav, sr, raw_segs, encoder)

    if not embeddings:
        return [{"start": s["start"], "end": s["end"], "speaker": "SPEAKER_00"} for s in raw_segs]

    arr = np.array(embeddings)

    durations = [raw_segs[i]["end"] - raw_segs[i]["start"] for i in valid_indices]
    speakers = cluster_speakers(arr, durations, n_speakers or "silhouette")
    seg_speakers = dict(zip(valid_indices, speakers))

    timeline = [
        {"start": seg["start"], "end": seg["end"], "speaker": seg_speakers.get(i, "SPEAKER_00")}
        for i, seg in enumerate(raw_segs)
    ]
    return _smooth_turns(timeline, min_turn_sec)


_REFINE_SAMPLE_BLOCKS = 30  # LLMに送る先頭ブロック数


def refine_speakers_with_llm(
    aligned: list[dict],
    llm_url: str,
    llm_model: str,
) -> list[dict]:
    """LLMを使って SPEAKER_XX ラベルを実名に補正する。

    会話の先頭ブロックから名前の呼びかけを検出し、
    {"SPEAKER_00": "田中", ...} のマッピングを生成して適用する。
    LLM が未起動・パース失敗の場合は元の aligned をそのまま返す。
    """
    import json as _json
    import re as _re
    from echonote import llm as _llm

    if not aligned:
        return aligned

    speakers = sorted({b["speaker"] for b in aligned})
    sample = aligned[:_REFINE_SAMPLE_BLOCKS]
    dialogue = "\n".join(f"[{b['speaker']}] {b['text'][:200]}" for b in sample)

    prompt = f"""以下は会議の文字起こしです。話者ラベル（SPEAKER_XX）が付いています。
会話の内容から各話者の実際の名前を推定してください。
名前が会話中に登場しない話者は SPEAKER_XX のままにしてください。

話者一覧: {', '.join(speakers)}

会話（先頭抜粋）:
{dialogue}

以下のJSON形式のみで回答してください（他のテキストは不要）:
{{"SPEAKER_00": "名前または SPEAKER_00", "SPEAKER_01": "名前または SPEAKER_01"}}"""

    try:
        response = "".join(_llm.complete(prompt, base_url=llm_url, model=llm_model, stream=True))
    except (_llm.LLMConnectionError, _llm.LLMError):
        return aligned

    match = _re.search(r'\{[^{}]+\}', response, _re.DOTALL)
    if not match:
        return aligned

    try:
        mapping: dict[str, str] = _json.loads(match.group())
    except _json.JSONDecodeError:
        return aligned

    return [
        {**b, "speaker": mapping.get(b["speaker"], b["speaker"])}
        for b in aligned
    ]


def align_text_to_speakers(
    text: str,
    timeline: list[dict],
) -> list[dict]:
    """テキストを話者タイムラインに基づいて話者ごとに分割する。

    各段落の文字位置中央を時間軸にマッピングし、その時刻の話者を割り当てる。
    段落境界を保持するため文の途中で切れない。

    Args:
        text: 貼り付けテキスト（タイムスタンプなし）
        timeline: diarize_standalone() の出力

    Returns:
        [{"speaker": str, "text": str}, ...]
    """
    import re

    if not text.strip() or not timeline:
        return [{"speaker": "SPEAKER_00", "text": text}]

    total_duration = max(seg["end"] for seg in timeline)

    def _speaker_at(t: float) -> str:
        """時刻 t の話者を返す。ギャップは最近傍セグメントで補完。"""
        for seg in timeline:
            if seg["start"] <= t <= seg["end"]:
                return seg["speaker"]
        nearest = min(timeline, key=lambda s: min(abs(s["start"] - t), abs(s["end"] - t)))
        return nearest["speaker"]

    # 段落で分割（\n\n → \n → 文区切りの順にフォールバック）
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if len(paragraphs) < 2:
        paragraphs = [p.strip() for p in re.split(r"\n", text) if p.strip()]
    if len(paragraphs) < 2:
        paragraphs = [p.strip() for p in re.split(r"(?<=[。！？])", text) if p.strip()]
    if not paragraphs:
        return [{"speaker": timeline[0]["speaker"], "text": text}]

    total_chars = sum(len(p) for p in paragraphs)
    if total_chars == 0:
        return [{"speaker": "SPEAKER_00", "text": text}]

    # 各段落の文字位置中央を時間軸にマッピングして話者を決定
    result: list[dict] = []
    char_pos = 0
    for para in paragraphs:
        center_time = (char_pos + len(para) / 2) / total_chars * total_duration
        speaker = _speaker_at(center_time)
        char_pos += len(para)

        if result and result[-1]["speaker"] == speaker:
            result[-1]["text"] += "\n\n" + para
        else:
            result.append({"speaker": speaker, "text": para})

    return result
