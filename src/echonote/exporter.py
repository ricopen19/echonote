"""出力生成 — Phase 1 は Markdown のみ。"""

from __future__ import annotations

from echonote.transcriber import Segment


def segments_to_text(segments: list[Segment]) -> str:
    """セグメントリストをプレーンテキストに変換する。"""
    return "\n".join(s["text"] for s in segments)


def segments_to_transcript(segments: list[Segment]) -> str:
    """タイムスタンプ付きのトランスクリプトテキストを返す。"""
    lines = []
    for s in segments:
        start = _fmt_time(s["start"])
        end = _fmt_time(s["end"])
        lines.append(f"[{start} - {end}] {s['text']}")
    return "\n".join(lines)


def to_markdown(content: str) -> str:
    return content


def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"
