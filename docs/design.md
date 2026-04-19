# Echonote — 設計仕様書

> 音声ファイルから構造化されたテキスト記録を生成するローカル完結型アプリケーション

## 1. 概要

### 1.1 プロダクトビジョン

Echonote は、音声ファイルをアップロードするだけで、文字起こし・話者分離・LLM による構造化を経て、すぐに使える記録ドキュメントを出力するツール。会議だけでなく、面接練習や授業の記録にも対応する汎用音声記録アプリ。

### 1.2 想定ユースケース

| ユースケース | 参加人数 | 出力に求められるもの |
|---|---|---|
| 定例ミーティング | 3〜10名 | 決定事項、アクションアイテム、議題ごとの要約 |
| ブレインストーミング | 3〜10名 | アイデア一覧、分類、結論 |
| 面接練習 | 2名 | 質疑応答の構造化、フィードバックポイント |
| 授業・講義の記録 | 1〜数名 | 要点整理、トピックごとの要約 |

### 1.3 ユーザーと対象ハードウェア

- 初期: 開発者本人（テスト）
- 展開: 同じ課のチームメンバー（各自のPCでローカル実行）

想定ハードウェアは 3 ティア:

| ティア | 代表マシン | RAM | GPU | 想定用途 |
|---|---|---|---|---|
| **Light** | 一体型 PC (Core i5-12500T) | 8GB | なし (iGPU のみ) | 短時間音声・軽量モデル |
| **Standard** | デスクトップ (Core i5-8500) | 16GB | なし (iGPU のみ) | 標準運用 |
| **Performance** | MacBook Air M5 | 32GB | Apple GPU (MPS) | 長時間音声・高精度 |

---

## 2. システムアーキテクチャ

### 2.1 全体構成

```
┌─────────────────────────────────────────┐
│         Gradio UI (ブラウザ)              │
│  - 音声アップロード                       │
│  - 話者ラベル編集                         │
│  - プロンプトテンプレート編集              │
│  - 出力プレビュー・ダウンロード            │
└──────────┬──────────────────────────────┘
           │ HTTP (localhost)
┌──────────▼──────────────────────────────┐
│       Python バックエンド                 │
│                                           │
│  ┌────────────────────┐ ┌──────────────┐ │
│  │ 転写エンジン        │ │ 話者分離      │ │
│  │  Mac: mlx-whisper   │ │ pyannote     │ │
│  │  Win: faster-whisper│ │ (device自動) │ │
│  └─────────┬──────────┘ └──────┬───────┘ │
│            └───────┬───────────┘         │
│             ┌──────▼──────────┐          │
│             │ テキスト統合     │          │
│             └──────┬──────────┘          │
│             ┌──────▼──────────────────┐  │
│             │ OpenAI 互換 LLM API     │  │
│             │  Mac: mlx_lm.server     │  │
│             │  Win: ollama serve      │  │
│             └──────┬──────────────────┘  │
│             ┌──────▼──────────┐          │
│             │ 出力生成          │          │
│             │ (.docx / .md)     │          │
│             └──────────────────┘          │
└─────────────────────────────────────────┘
```

### 2.2 処理フロー（順次実行・RAM節約）

メモリ制約のあるマシン（8GB〜）を考慮し、各ステップを順次実行してモデルをアンロードする。

```
Step 1: 音声アップロード・バリデーション
    ↓
Step 2: 転写
         Mac → mlx-whisper (MLX ネイティブ)
         Win → faster-whisper (CPU int8 / CUDA)
         → 結果保持 → モデル解放
    ↓
Step 3: pyannote-audio で話者分離（オプション）
         device 自動: MPS (Mac) / CUDA (Win+GPU) / CPU (fallback)
         → 結果保持 → モデル解放
    ↓
Step 4: 文字起こし + 話者情報をマージ
    ↓
Step 5: UI上で話者ラベルを人名に手動割り当て
    ↓
Step 6: プロンプトテンプレート選択・編集
    ↓
Step 7: OpenAI 互換 LLM エンドポイントに構造化を依頼
         Mac → mlx_lm.server (http://localhost:8080/v1)
         Win → ollama serve (http://localhost:11434/v1)
    ↓
Step 8: プレビュー → Word (.docx) / Markdown (.md) でダウンロード
```

### 2.3 推定メモリ使用量（ティア別）

**Light (8GB PC)** — 一体型 i5-12500T など

| ステップ | ピークRAM | 備考 |
|---|---|---|
| Step 2: faster-whisper (tiny/small) | ~200〜500MB | tiny は 39M / small は 244M params |
| Step 3: pyannote (CPU) | ~1.5GB | 長時間音声は非推奨 |
| Step 7: LLM (Qwen3-1.7B 4bit) | ~1.5GB | 別プロセスで常駐 |
| OS + Gradio + Python | ~3GB | ベースライン (Windows + 常駐アプリ込み) |
| **同時最大** | **~6GB** | 順次実行で Step 2↔3↔7 を重ねない |

**Standard (16GB PC)** — i5-8500 など

| ステップ | ピークRAM | 備考 |
|---|---|---|
| Step 2: faster-whisper (medium) | ~1.5GB | 769M params |
| Step 3: pyannote (CPU) | ~1.5GB | |
| Step 7: LLM (Qwen3-4B 4bit) | ~3GB | 別プロセスで常駐 |
| OS + Gradio + Python | ~4GB | ベースライン |
| **同時最大** | **~8.5GB** | 順次実行により抑制 |

**Performance (32GB Mac)** — M5 Apple Silicon

| ステップ | ピークRAM | 備考 |
|---|---|---|
| Step 2: mlx-whisper (large-v3-turbo) | ~2GB | MLX ネイティブ、GPU 共有メモリ |
| Step 3: pyannote (MPS) | ~1GB | MPS で CPU 比 10x+ 高速 |
| Step 7: LLM (Qwen3.5-35B-A3B 4bit) | ~20GB | mlx_lm.server 常駐 |
| OS + Gradio + Python | ~4GB | ベースライン |
| **同時最大** | **~25GB** | LLM 常駐、転写/分離は都度解放 |

---

## 3. コンポーネント詳細

### 3.1 音声入力

- **対応形式**: mp3, wav, m4a, ogg, flac, webm
- **最大ファイルサイズ**: 500MB（設定で変更可能）
- **バリデーション**: ffprobe で形式・長さを事前チェック
- **将来拡張**: リアルタイム録音対応（v2 以降）

### 3.2 文字起こし（プラットフォーム別）

プラットフォームで実装を切り替える。設定ファイル or 環境変数 (`ECHONOTE_TRANSCRIBE_BACKEND`) で明示切替も可能。

#### Mac (Apple Silicon) — mlx-whisper

- **モデル**: `mlx-community/whisper-large-v3-turbo` デフォルト (~1.5GB、4bit)
- **速度**: MBA M5 で 11.5x リアルタイム (9分音声を 47秒)
- **選択可能**: `whisper-large-v3` (高精度、~3GB、速度は半分)
- **デバイス**: MLX (GPU 共有メモリ、自動)

#### Windows / Linux — faster-whisper

- **デフォルトモデル**: ティア別
  - Light (8GB): `tiny` or `small`
  - Standard (16GB): `medium`
  - Performance (16GB+ with GPU): `large-v3`
- **選択可能**: tiny / base / small / medium / large-v3 / large-v3-turbo
- **言語**: 日本語 (`ja`) をデフォルト、自動検出も可能
- **デバイス**: CPU (`int8`) をデフォルト、CUDA 対応（GPU搭載機向け）

#### 将来検討

- faster-whisper より高速な代替 (whisper.cpp、distil-whisper、Kotoba-Whisper 等) を Windows 側で検討予定
- MLX 側も量子化バリアントで更に高速化できる可能性

#### 出力 (実装共通)

```python
# プラットフォーム非依存の出力形式
[
    {"start": 0.0, "end": 3.5, "text": "それでは定例を始めます"},
    {"start": 3.8, "end": 7.2, "text": "今週の進捗を共有してください"},
    ...
]
```

### 3.3 話者分離（pyannote-audio）— オプション機能

- **ライブラリ**: pyannote.audio（HuggingFace トークン・利用同意が必要）
- **有効/無効**: UI のトグルで切り替え
- **処理**: 話者分離結果をタイムスタンプで文字起こしセグメントにマージ
- **話者ラベル**: `SPEAKER_01`, `SPEAKER_02`, ... → UI 上で人名に手動マッピング
- **フォールバック**: pyannote が使えない環境では、話者分離なしで動作

#### デバイス自動判定

```python
import torch
if torch.backends.mps.is_available():
    device = "mps"       # Mac Apple Silicon (10倍以上速い)
elif torch.cuda.is_available():
    device = "cuda"      # Windows/Linux with NVIDIA
else:
    device = "cpu"       # fallback (長時間音声は非推奨)
```

**Mac での測定値 (33分音声)**: CPU 30 分+ → MPS 130 秒。**MPS 利用は Mac では必須**。

#### 既知の互換性パッチ (2026-04 時点)

pyannote + 新しい PyTorch / huggingface_hub との非互換を吸収する 3 点:

| 症状 | 対処 |
|---|---|
| `Weights only load failed` (PyTorch 2.6+) | `torch.load` をモンキーパッチし `weights_only=False` を強制 |
| `hf_hub_download() got an unexpected keyword argument 'use_auth_token'` | `hf_hub_download` をラップし `use_auth_token` → `token` に変換 |
| `whisperx.diarize` モジュールが属性として解決されない | `from whisperx.diarize import DiarizationPipeline, assign_word_speakers` と明示 import |

#### 進行バー

pyannote の `ProgressHook` を渡すと 4 フェーズ (segmentation / speaker_counting / embeddings / discrete_diarization) の tqdm が出る。Python の stdout バッファリングで即時表示されない場合は `PYTHONUNBUFFERED=1` または `print(..., flush=True)` を併用する。

#### マージ後の出力イメージ

```python
[
    {"start": 0.0, "end": 3.5, "speaker": "田中", "text": "それでは定例を始めます"},
    {"start": 3.8, "end": 7.2, "speaker": "佐藤", "text": "今週の進捗を共有してください"},
    ...
]
```

### 3.4 LLM 構造化（OpenAI 互換エンドポイント）

バックエンド依存をコードに持ち込まないため、**OpenAI 互換 API を叩くクライアント**として抽象化する。ユーザーは自 OS に合ったサーバーを別途起動する。

#### エンドポイント設定

| 環境 | サーバー | URL | 代表モデル |
|---|---|---|---|
| Mac | `mlx_lm.server` | `http://localhost:8080/v1` | `mlx-community/Qwen3.5-35B-A3B-4bit` |
| Windows/Linux | `ollama serve` | `http://localhost:11434/v1` | `qwen3:4b-q4_K_M` |

- 設定項目は `ECHONOTE_LLM_URL` / `ECHONOTE_LLM_MODEL`（UI で編集可）
- クライアントは `openai` SDK または `requests` で `/v1/chat/completions` を呼ぶ
- ストリーミング対応（生成中にリアルタイム表示）

#### モデル選定の指針

| ティア | 推奨モデル | 備考 |
|---|---|---|
| Light (8GB) | Qwen3-1.7B 4bit (~1GB) / Gemma 3 1B | 日本語品質は最低限、要約用途に限定 |
| Standard (16GB) | Qwen3-4B 4bit (~2.5GB) | 日常用途で十分な品質 |
| Performance (32GB, Mac) | Qwen3.5-35B-A3B 4bit (~19GB) | MoE で 3B active 相当の速度、57 tok/s 出る |

#### プリセットテンプレート

**会議議事録**
```
以下は会議の文字起こしです。これを議事録として構造化してください。

## 出力フォーマット
- 会議概要（1〜2文）
- 議題ごとの要約
- 決定事項
- アクションアイテム（担当者・期限があれば記載）
- 次回予定（言及があれば）

## 文字起こし
{transcript}
```

**面接練習**
```
以下は面接練習の文字起こしです。構造化してフィードバックを生成してください。

## 出力フォーマット
- 質疑応答の一覧（Q&A形式）
- 回答の良かった点
- 改善が必要な点
- 総合コメント

## 文字起こし
{transcript}
```

**授業・講義**
```
以下は授業/講義の文字起こしです。学習ノートとして構造化してください。

## 出力フォーマット
- 授業のテーマ
- トピックごとの要点整理
- 重要な用語・概念
- まとめ

## 文字起こし
{transcript}
```

**カスタム**: ユーザーが自由に編集可能

### 3.5 出力生成

- **Markdown (.md)**: そのまま文字列として出力
- **Word (.docx)**: `python-docx` で生成。見出し・箇条書き・表を適切にフォーマット
- **プレビュー**: Gradio 上で Markdown レンダリングして確認
- **ダウンロード**: ファイルとしてダウンロード

---

## 4. UI 設計（Gradio）

### 4.1 画面構成

```
┌──────────────────────────────────────────────────┐
│  Echonote 🎧                                      │
├──────────────────────────────────────────────────┤
│                                                    │
│  [Tab 1: 文字起こし]  [Tab 2: 記録生成]  [Tab 3: 設定] │
│                                                    │
│  ─── Tab 1: 文字起こし ───                          │
│                                                    │
│  ┌──────────────────┐  ┌──────────────────────┐   │
│  │ 音声ファイル       │  │ オプション            │   │
│  │ [ドラッグ&ドロップ] │  │ モデル: [medium ▼]   │   │
│  │                   │  │ 言語:   [日本語 ▼]    │   │
│  │                   │  │ ☑ 話者分離を有効にする  │   │
│  └──────────────────┘  └──────────────────────┘   │
│                                                    │
│  [▶ 文字起こし開始]                                  │
│                                                    │
│  進捗: ████████░░ 80%  Step 2/3: 話者分離中...      │
│                                                    │
│  ─── 文字起こし結果 ───                              │
│  [00:00 - 00:03] Speaker 1: それでは定例を始めます    │
│  [00:03 - 00:07] Speaker 2: 今週の進捗を共有して...   │
│                                                    │
│  ─── 話者ラベル編集 ───                              │
│  Speaker 1 → [田中      ]                           │
│  Speaker 2 → [佐藤      ]                           │
│                                                    │
├──────────────────────────────────────────────────┤
│  ─── Tab 2: 記録生成 ───                            │
│                                                    │
│  テンプレート: [会議議事録 ▼]                         │
│  ┌──────────────────────────────────────────┐      │
│  │ プロンプト（編集可能）                       │      │
│  │ 以下は会議の文字起こしです。これを議事録...    │      │
│  └──────────────────────────────────────────┘      │
│                                                    │
│  [▶ 記録を生成]                                     │
│                                                    │
│  ─── 生成結果プレビュー ───                          │
│  ## 会議概要                                        │
│  〇〇プロジェクトの進捗確認会議...                    │
│                                                    │
│  [📥 Markdown] [📥 Word]                            │
│                                                    │
├──────────────────────────────────────────────────┤
│  ─── Tab 3: 設定 ───                               │
│                                                    │
│  LLM エンドポイント URL:                             │
│    [http://localhost:8080/v1]  (Mac mlx-lm)         │
│    [http://localhost:11434/v1] (Win Ollama)         │
│  LLM モデル: [Qwen3.5-35B-A3B-4bit  ]               │
│  HuggingFace トークン: [**********  ]（話者分離用）  │
│  デフォルト言語: [日本語 ▼]                           │
│  デフォルトモデル: [medium ▼]                         │
│                                                    │
└──────────────────────────────────────────────────┘
```

### 4.2 クロスプラットフォーム対応

- Gradio はブラウザベースのため、Windows / Mac 両対応
- Python 3.10+ をサポート
- `uv sync` で依存関係をすべてインストール
- プラットフォーム依存の依存 (`mlx-whisper`, `mlx-lm`) は optional extras で分離

---

## 5. 技術スタック

| カテゴリ | 技術 | バージョン | プラットフォーム |
|---|---|---|---|
| 言語 | Python | 3.10+ | 共通 |
| パッケージ管理 | uv (pyproject.toml) | — | 共通 |
| 転写 (共通フォールバック) | faster-whisper | 1.2.x | Windows/Linux、Mac でも動作 |
| 転写 (Mac 最適化) | mlx-whisper | 最新 | Mac (optional) |
| 話者分離 | pyannote.audio | 3.x | 共通 (device 自動) |
| 互換性補助 | whisperx | 3.7.x | pyannote 周りのラッパーとして流用 |
| LLM サーバー (Mac) | mlx-lm (`mlx_lm.server`) | 最新 | Mac (別プロセス) |
| LLM サーバー (Win/Linux) | Ollama | 最新 | Windows/Linux (別プロセス) |
| LLM クライアント | openai SDK or requests | — | 共通 |
| GUI | Gradio | 5.x | 共通 |
| Word 出力 | python-docx | — | 共通 |
| 音声処理 | ffmpeg (システム依存) | — | 共通 |

---

## 6. プロジェクト構成

```
echonote/
├── pyproject.toml
├── README.md
├── docs/
│   ├── design.md          ← 本ファイル
│   └── tasks.md           ← タスク一覧
├── src/
│   └── echonote/
│       ├── __init__.py
│       ├── app.py          ← Gradio アプリ（エントリーポイント）
│       ├── transcriber.py  ← mlx-whisper / faster-whisper の切替ラッパー
│       ├── diarizer.py     ← pyannote ラッパー（device 自動、互換性パッチ込み）
│       ├── llm.py          ← OpenAI 互換 API クライアント
│       ├── exporter.py     ← .docx / .md 出力
│       ├── prompts/
│       │   ├── meeting.txt
│       │   ├── interview.txt
│       │   └── lecture.txt
│       └── config.py       ← 設定管理（HW ティア検出、endpoint 切替）
├── tests/
│   ├── test_transcriber.py
│   ├── test_diarizer.py
│   ├── test_llm.py
│   └── test_exporter.py
└── .gitignore
```

---

## 7. 前提条件・外部依存

ユーザーが事前にインストール・設定しておく必要があるもの。

### 共通

1. **Python 3.10+**
2. **ffmpeg** — 音声ファイルのデコードに必要
3. **HuggingFace トークン**（話者分離を使う場合）
   - `pyannote/speaker-diarization-3.1` と `pyannote/segmentation-3.0` で利用規約同意
   - `HF_TOKEN` 環境変数に設定

### Mac (Apple Silicon)

```bash
# uv で依存を入れる
uv sync --extra mac

# LLM サーバーを起動（別ターミナル）
uv run mlx_lm.server --model mlx-community/Qwen3.5-35B-A3B-4bit
# → http://localhost:8080/v1 で OpenAI 互換 API
```

### Windows / Linux

```bash
# uv で依存を入れる
uv sync

# Ollama を別途インストール
# macOS/Win: https://ollama.com/download
ollama pull qwen3:4b-q4_K_M
ollama serve
# → http://localhost:11434/v1 で OpenAI 互換 API
```

---

## 8. 制約・リスク

| リスク | 影響 | 対策 |
|---|---|---|
| Light ティア (8GB) でのメモリ不足 | 長時間音声で処理が遅い・失敗 | tiny/small モデル固定、短時間音声推奨 |
| pyannote の CPU 推論が遅い | Windows 無 GPU 環境で実用性低下 | オプション化、短時間音声の場合のみ推奨 |
| Mac M5 で Ollama が動かない (Metal バグ) | Ollama バックエンドが使えない | mlx-lm に切替 (`mlx_lm.server`) を必須ルートに |
| LLM モデルの日本語精度 | 出力品質が不十分 | プロンプト調整、モデル変更可能に |
| LLM サーバー未起動時のエラー | ユーザー混乱 | 起動チェック・エンドポイント到達性確認、ガイド表示 |
| ffmpeg 未インストール | 音声読み込み失敗 | セットアップガイドで明記 |
| pyannote の新 PyTorch 非互換 | モデル読み込み時エラー | `torch.load` / `hf_hub_download` のモンキーパッチ (§3.3 参照) |

---

## 9. フェーズ分け

### Phase 1 — MVP（最小動作版）
- 音声アップロード → 転写（プラットフォーム別）→ LLM（OpenAI 互換）で構造化 → Markdown 出力
- Gradio UI（基本レイアウト）
- プロンプトテンプレート（会議議事録のみ）
- **優先ターゲット: Standard ティア (16GB Win)**

### Phase 2 — 話者分離・出力拡充
- pyannote-audio による話者分離（オプション、device 自動）
- 話者ラベル手動編集
- Word (.docx) 出力対応
- テンプレート追加（面接・授業）
- Mac (Performance ティア) での最適化 (mlx-whisper 経路)

### Phase 3 — UX改善・展開
- 進捗表示の改善（pyannote ProgressHook、faster-whisper `print_progress`）
- 設定の永続化
- セットアップスクリプト / ドキュメント整備（Mac / Win それぞれ）
- Light ティア (8GB 一体型) 向けモデル最適化
- チームメンバーへの展開

### Phase 4（将来）
- リアルタイム録音対応
- 過去の記録の管理・検索
- 話者の声紋登録による自動識別
- faster-whisper より高速な転写エンジン検討 (whisper.cpp / distil-whisper / Kotoba-Whisper 等)
