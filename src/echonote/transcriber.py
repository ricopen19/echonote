"""転写モジュール — faster-whisper ラッパー。プラットフォーム統一出力を返す。"""

from __future__ import annotations

import shutil
import sys
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from echonote.config import Settings

Segment = dict  # {"start": float, "end": float, "text": str}

WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v2", "large-v3", "large-v3-turbo"]


def _check_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg が見つかりません。インストールしてください。\n"
            "  Windows: https://ffmpeg.org/download.html\n"
            "  Mac: brew install ffmpeg"
        )


def _stream_faster_whisper(
    audio_path: str,
    model_size: str,
    language: str,
    device: str = "cpu",
    compute_type: str = "int8",
):
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    try:
        segments, _ = model.transcribe(audio_path, language=language, beam_size=5)
        for s in segments:
            yield {"start": s.start, "end": s.end, "text": s.text.strip()}
    finally:
        del model


def _stream_mlx_whisper(
    audio_path: str,
    model_size: str,
    language: str,
):
    import mlx_whisper

    _MODEL_MAP = {
        "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
        "large-v3": "mlx-community/whisper-large-v3",
        "medium": "mlx-community/whisper-medium",
        "small": "mlx-community/whisper-small",
        "base": "mlx-community/whisper-base",
        "tiny": "mlx-community/whisper-tiny",
    }
    repo = _MODEL_MAP.get(model_size, f"mlx-community/whisper-{model_size}")
    result = mlx_whisper.transcribe(audio_path, path_or_hf_repo=repo, language=language)
    # mlx-whisper はバッチ処理なのでまとめて yield
    for s in result["segments"]:
        yield {"start": s["start"], "end": s["end"], "text": s["text"].strip()}


def transcribe_stream(
    audio_path: str | Path,
    model_size: str,
    language: str,
    settings: Settings | None = None,
):
    """音声ファイルを転写し、セグメントを順次 yield する。"""
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
        except Exception:
            # ImportError（未インストール）またはモデル取得失敗など → faster-whisper にフォールバック
            traceback.print_exc()
            print("[transcriber] mlx-whisper 失敗 → faster-whisper にフォールバック", flush=True)

    yield from _stream_faster_whisper(audio_path, model_size, language)


def transcribe(
    audio_path: str | Path,
    model_size: str,
    language: str,
    settings: Settings | None = None,
) -> list[Segment]:
    """音声ファイルを転写して [{start, end, text}] を返す。"""
    return list(transcribe_stream(audio_path, model_size, language, settings))
