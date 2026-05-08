"""話者分離モジュール — resemblyzer（優先）/ pyannote-audio（フォールバック）。"""

from __future__ import annotations

import functools
import gc
from pathlib import Path

_CLUSTER_THRESHOLD = 0.65  # AgglomerativeClustering の cosine 距離閾値


# ── resemblyzer ───────────────────────────────────────────────────────────────

def _diarize_resemblyzer(audio_path: str, segments: list[dict]) -> list[dict]:
    import sys, types
    # webrtcvad が pkg_resources.get_distribution を version 取得にのみ使うため、uv 環境向けにスタブを注入
    if "pkg_resources" not in sys.modules:
        _stub = types.ModuleType("pkg_resources")
        _stub.get_distribution = lambda name: type("D", (), {"version": "0.0.0"})()
        sys.modules["pkg_resources"] = _stub
    from resemblyzer import VoiceEncoder, preprocess_wav
    import numpy as np
    from sklearn.cluster import AgglomerativeClustering

    wav = preprocess_wav(audio_path)
    sr = 16_000
    encoder = VoiceEncoder("cpu")

    embeddings: list = []
    valid_indices: list[int] = []
    for i, seg in enumerate(segments):
        chunk = wav[int(seg["start"] * sr) : int(seg["end"] * sr)]
        if len(chunk) < int(sr * 0.5):
            continue
        embeddings.append(encoder.embed_utterance(chunk))
        valid_indices.append(i)

    if not embeddings:
        return [{**seg, "speaker": "SPEAKER_00"} for seg in segments]

    arr = np.array(embeddings)
    if len(arr) == 1:
        raw_labels = [0]
    else:
        raw_labels = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=_CLUSTER_THRESHOLD,
            metric="cosine",
            linkage="average",
        ).fit_predict(arr).tolist()

    label_map: dict[int, str] = {}
    seg_speakers: dict[int, str] = {}
    for idx, label in zip(valid_indices, raw_labels):
        if label not in label_map:
            label_map[label] = f"SPEAKER_{len(label_map):02d}"
        seg_speakers[idx] = label_map[label]

    return [
        {**seg, "speaker": seg_speakers.get(i, "SPEAKER_00")}
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


def _assign_speakers(diarization, segments: list[dict]) -> list[dict]:
    """話者区間をセグメントに割り当てる（最大重複時間で判定）。"""
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


# ── 公開 API ──────────────────────────────────────────────────────────────────

def diarize(
    audio_path: str | Path,
    hf_token: str,
    segments: list[dict],
) -> list[dict]:
    """話者分離を実行し、各セグメントに speaker キーを付加して返す。

    resemblyzer が利用可能な場合は HF トークン不要で実行する。
    未インストールの場合は pyannote-audio にフォールバックする（HF トークン必須）。
    """
    audio_path = str(audio_path)

    try:
        import resemblyzer  # noqa: F401
        return _diarize_resemblyzer(audio_path, segments)
    except ImportError:
        pass

    if not hf_token:
        raise ValueError(
            "HuggingFace トークンが未設定です。設定タブで HF_TOKEN を入力してください。"
        )
    return _diarize_pyannote(audio_path, hf_token, segments)
