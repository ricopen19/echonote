# Echonote — 検討中の仕様

> Phase 1 実装済み内容はコードを参照。このファイルには未実装・検討中のみ残す。

---

## Phase 2: 話者分離（pyannote-audio）

### 概要

- pyannote.audio でオプション話者分離を追加
- UI にトグルスイッチ、話者ラベル手動マッピング
- Word (.docx) 出力対応

### メモリ管理（重要）

Windows 検証で OOM が確認されたため、Phase 2 実装時は以下の順序を厳守する：

```
転写（faster-whisper）→ モデル解放
  ↓
話者分離（pyannote）→ モデル解放
  ↓
LLM 生成（Ollama、keep_alive=0 で即アンロード）
```

各ステップ間でモデルを解放しないと 16GB 環境でも OOM になる。
pyannote は CPU で約 1.5GB、MPS/CUDA では約 1GB。

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
Windows 無 GPU: CPU のみ → 長時間音声は非現実的。UI でオプション化し短時間推奨。

### 既知の互換性パッチ（2026-04 時点）

| 症状 | 対処 |
|---|---|
| `Weights only load failed` (PyTorch 2.6+) | `torch.load` をモンキーパッチし `weights_only=False` を強制 |
| `hf_hub_download() got an unexpected keyword argument 'use_auth_token'` | `use_auth_token` → `token` に変換するラッパーを噛ませる |
| `whisperx.diarize` が属性として解決されない | `from whisperx.diarize import DiarizationPipeline, assign_word_speakers` と明示 import |

---

## Phase 2: テンプレート追加

- `prompts/interview.txt` — 面接練習（Q&A構造化・フィードバック）
- `prompts/lecture.txt` — 授業・講義（要点整理・用語抽出）

---

## Phase 3: 将来検討

- 設定の永続化（TOML ファイル）
- 進捗表示の改善（pyannote ProgressHook 連携）
- 長時間音声のチャンク分割（10分単位で転写→結合、OOM 対策）
- Light ティア向け転写エンジン検討（whisper.cpp / distil-whisper / Kotoba-Whisper）
- Mac mlx-whisper 転写経路の最適化

---

## 制約・リスク（未解決）

| リスク | 状況 | 対策候補 |
|---|---|---|
| 16GB + medium + 長時間音声で OOM | 確認済み | `keep_alive=0` で改善、チャンク分割（P3-7）が根本解決 |
| 8GB で pyannote が OOM | 未検証（ほぼ確実） | 話者分離を完全オプション化、Light ティアでは非表示も検討 |
| Windows で CUDA 有無をどう検出するか | 未実装 | Phase 2 で `torch.cuda.is_available()` を config.py に追加 |
| mlx-community の small/medium モデル名が存在しない | 確認済み | 404 は静かに faster-whisper へフォールバック（実装済み） |
