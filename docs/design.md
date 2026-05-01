# Echonote — 検討中の仕様

> Phase 1 実装済み内容はコードを参照。このファイルには未実装・検討中のみ残す。

---

## Phase 2: 話者分離（pyannote-audio）

### 概要

- pyannote.audio でオプション話者分離を追加
- UI にトグルスイッチ、話者ラベル手動マッピング
- Word (.docx) 出力対応

### device 自動判定

```python
import torch
if torch.backends.mps.is_available():
    device = "mps"
elif torch.cuda.is_available():
    device = "cuda"
else:
    device = "cpu"
```

Mac MPS: 33分音声で 130秒（CPU だと 30分以上）。

### 既知の互換性パッチ（2026-04 時点）

| 症状 | 対処 |
|---|---|
| `Weights only load failed` (PyTorch 2.6+) | `torch.load` をモンキーパッチし `weights_only=False` を強制 |
| `hf_hub_download() got an unexpected keyword argument 'use_auth_token'` | `use_auth_token` → `token` に変換するラッパーを噛ませる |
| `whisperx.diarize` が属性として解決されない | `from whisperx.diarize import DiarizationPipeline, assign_word_speakers` と明示 import |

### Light ティア制約

Windows 無 GPU 環境では CPU 推論のみ → 長時間音声は非現実的。UI でオプション化し、短時間音声の場合のみ推奨するメッセージを出す。

---

## Phase 2: テンプレート追加

- `prompts/interview.txt` — 面接練習（Q&A構造化・フィードバック）
- `prompts/lecture.txt` — 授業・講義（要点整理・用語抽出）

---

## Phase 3: 将来検討

- 設定の永続化（TOML ファイル）
- 進捗表示の改善（pyannote ProgressHook 連携）
- Light ティア向け転写エンジン検討（whisper.cpp / distil-whisper / Kotoba-Whisper）
- Mac mlx-whisper 転写経路の mlx_lm.server との組み合わせ最適化

---

## 制約・リスク（未解決）

| リスク | 対策候補 |
|---|---|
| Light ティア (8GB) で pyannote が OOM | 話者分離を完全オプション化、短時間音声ガイド |
| LLM 日本語精度がティアによって大きく異なる | プロンプト調整 UI を充実させる |
| Windows で CUDA 有無をどう検出するか | Phase 2 で `torch.cuda.is_available()` を config.py に追加 |
