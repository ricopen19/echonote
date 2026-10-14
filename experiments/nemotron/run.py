"""Nemotron 3 Diarization 実行。stdout は JSON 配列のみ、ログは stderr。

usage: python run.py <audio_path>
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main(audio_path: str) -> None:
    # stdout は JSON 専用のプロトコル。NeMo の logger・C 拡張・子プロセスが fd 1 に書いても
    # 混ざらないよう、import 前に fd 1 を stderr に付け替え、元の stdout は JSON 出力用に退避する
    out = os.fdopen(os.dup(1), "w")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    import torch
    from nemo.collections.asr.models import SortformerEncLabelModel

    with tempfile.TemporaryDirectory() as tmp:
        wav = str(Path(tmp) / "in.wav")
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", wav],
            check=True, stdout=sys.stderr, stderr=sys.stderr,
        )
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        for dev in dict.fromkeys([device, "cpu"]):  # MPS で落ちたら CPU 固定
            try:
                model = SortformerEncLabelModel.from_pretrained(
                    "nvidia/Nemotron-3-Diarization", map_location=dev
                ).to(dev).eval()
                m = model.sortformer_modules
                m.chunk_len, m.chunk_right_context = 340, 40
                m.fifo_len, m.spkcache_update_period = 40, 300
                m._check_streaming_parameters()
                lines = model.diarize(audio=[wav], batch_size=1)[0]
                print(f"[nemotron] device={dev}", file=sys.stderr)
                break
            except Exception as e:
                if dev == "cpu":
                    raise
                print(f"[nemotron] {dev} 失敗、CPU へ: {e!r}", file=sys.stderr)

    turns = []
    for line in lines:
        s, e, spk = line.split()
        n = int(spk.split("_")[-1])
        turns.append({"start": float(s), "end": float(e), "speaker": f"SPEAKER_{n:02d}"})
    turns.sort(key=lambda t: t["start"])
    json.dump(turns, out)
    out.flush()


if __name__ == "__main__":
    main(sys.argv[1])
