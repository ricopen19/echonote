"""話者分離モジュール — resemblyzer（優先）/ pyannote-audio（フォールバック）。"""

from __future__ import annotations

import functools
import gc
from pathlib import Path

_CLUSTER_THRESHOLD = 0.45  # AgglomerativeClustering の cosine 距離閾値


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
    import sys
    import types

    if "pkg_resources" not in sys.modules:
        _stub = types.ModuleType("pkg_resources")
        _stub.get_distribution = lambda name: type("D", (), {"version": "0.0.0"})()
        sys.modules["pkg_resources"] = _stub

    import numpy as np
    import webrtcvad
    from resemblyzer import VoiceEncoder, preprocess_wav
    from sklearn.cluster import AgglomerativeClustering

    audio_path = str(audio_path)
    wav = preprocess_wav(audio_path)
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

    # Embeddings
    encoder = VoiceEncoder("cpu")
    embeddings: list = []
    valid_indices: list[int] = []
    for i, seg in enumerate(raw_segs):
        chunk = wav[int(seg["start"] * sr) : int(seg["end"] * sr)]
        if len(chunk) >= int(sr * 0.5):
            embeddings.append(encoder.embed_utterance(chunk))
            valid_indices.append(i)

    if not embeddings:
        return [{"start": s["start"], "end": s["end"], "speaker": "SPEAKER_00"} for s in raw_segs]

    arr = np.array(embeddings)

    # クラスタリング
    if n_speakers is not None:
        k = min(max(2, n_speakers), len(arr))
        if k < 2:
            raw_labels: list[int] = [0] * len(arr)
        else:
            raw_labels = AgglomerativeClustering(
                n_clusters=k, metric="cosine", linkage="average"
            ).fit_predict(arr).tolist()
    elif len(arr) < 2:
        raw_labels = [0] * len(arr)
    else:
        # シルエットスコアで最適k自動検出
        from sklearn.metrics import silhouette_score

        max_k = min(12, len(arr) - 1)
        best_k, best_score = 2, -1.0
        for k in range(2, max_k + 1):
            labels = AgglomerativeClustering(
                n_clusters=k, metric="cosine", linkage="average"
            ).fit_predict(arr)
            score = float(silhouette_score(arr, labels, metric="cosine"))
            if score > best_score:
                best_score, best_k = score, k
        raw_labels = AgglomerativeClustering(
            n_clusters=best_k, metric="cosine", linkage="average"
        ).fit_predict(arr).tolist()

    # 発話時間が全体の3%未満の話者を最近傍クラスタに統合（n_speakers 指定時も適用）
    if len(set(raw_labels)) > 1:
        label_times: dict[int, float] = {}
        for idx, lbl in zip(valid_indices, raw_labels):
            dur = raw_segs[idx]["end"] - raw_segs[idx]["start"]
            label_times[lbl] = label_times.get(lbl, 0.0) + dur

        min_time = sum(label_times.values()) * 0.03
        valid_lbls = {lbl for lbl, t in label_times.items() if t >= min_time}

        if len(valid_lbls) < len(set(raw_labels)):
            centroids = {
                lbl: arr[[i for i, l in enumerate(raw_labels) if l == lbl]].mean(axis=0)
                for lbl in set(raw_labels)
            }
            remap: dict[int, int] = {}
            for lbl in set(raw_labels):
                if lbl not in valid_lbls:
                    best_l, best_d = lbl, float("inf")
                    for other in valid_lbls:
                        c1, c2 = centroids[lbl], centroids[other]
                        d = 1.0 - float(
                            np.dot(c1, c2) / (np.linalg.norm(c1) * np.linalg.norm(c2) + 1e-8)
                        )
                        if d < best_d:
                            best_d, best_l = d, other
                    remap[lbl] = best_l
                else:
                    remap[lbl] = lbl
            raw_labels = [remap[l] for l in raw_labels]

    # 話者名マッピング（出現順）
    label_map: dict[int, str] = {}
    seg_speakers: dict[int, str] = {}
    for idx, lbl in zip(valid_indices, raw_labels):
        if lbl not in label_map:
            label_map[lbl] = f"SPEAKER_{len(label_map):02d}"
        seg_speakers[idx] = label_map[lbl]

    timeline = [
        {"start": seg["start"], "end": seg["end"], "speaker": seg_speakers.get(i, "SPEAKER_00")}
        for i, seg in enumerate(raw_segs)
    ]
    return _smooth_turns(timeline, min_turn_sec)


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
