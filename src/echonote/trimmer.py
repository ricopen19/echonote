"""音声トリミング — ffmpeg ラッパー。"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def get_duration(input_path: str) -> float:
    """ffprobe で音声の総時間（秒）を返す。失敗時は 0.0。"""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                input_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def trim(input_path: str, start_sec: float, end_sec: float) -> str:
    """音声を [start_sec, end_sec] にトリミングして tmp ファイルパスを返す。

    end_sec <= 0 は「末尾まで」として扱う。
    コーデックコピーのため高速だが、keyframe 境界から数フレームのズレが生じる場合がある。
    """
    suffix = Path(input_path).suffix or ".mp3"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.close()

    cmd = ["ffmpeg", "-y", "-i", input_path]
    if start_sec > 0:
        cmd += ["-ss", str(start_sec)]
    if end_sec > 0:
        cmd += ["-to", str(end_sec)]
    cmd += ["-c", "copy", tmp.name]

    subprocess.run(cmd, check=True, capture_output=True)
    return tmp.name
