# Echonote — タスク一覧

## Phase 1 MVP（Windows Standard ティア優先）

**目標**: 音声アップロード → faster-whisper 転写 → Ollama LLM 構造化 → Markdown 出力 → Gradio UI

### Claude Code 担当

| ID | タスク | ファイル | 状態 |
|---|---|---|---|
| T1 | プラットフォーム・HWティア検出、設定管理 | `src/echonote/config.py` | ✅ 完了 |
| T2 | faster-whisper ラッパー（統一出力フォーマット） | `src/echonote/transcriber.py` | ✅ 完了 |
| T3 | OpenAI互換 LLM クライアント（到達性確認・ストリーミング） | `src/echonote/llm.py` | ✅ 完了 |
| T4 | Gradio UI（Tab構成・処理フロー接続） | `src/echonote/app.py` | ✅ 完了 |

### Antigravity 担当

| ID | タスク | ファイル | 状態 |
|---|---|---|---|
| A1 | Markdown 整形出力 | `src/echonote/exporter.py` | ✅ 完了（Claude Codeで実施） |
| A2 | 会議議事録プロンプトテンプレート | `src/echonote/prompts/meeting.txt` | ✅ 完了（Claude Codeで実施） |
| A3 | transcriber ユニットテスト（faster-whisper モック） | `tests/test_transcriber.py` | 未着手 |
| A4 | llm クライアントのユニットテスト（requests モック） | `tests/test_llm.py` | 未着手 |
| A5 | exporter のユニットテスト | `tests/test_exporter.py` | 未着手 |

### 設計上の決定事項（Phase 1）

- LLM クライアント: `requests`（pyproject.toml 既存依存）
- HWティア検出: `psutil` で総RAM取得 → 8GB未満=Light / 12GB未満=Standard / それ以上=Performance。`ECHONOTE_HW_TIER` 環境変数で上書き可
- 話者分離（diarizer.py）: Phase 2 以降
- Word 出力（.docx）: Phase 2 以降

---

## Phase 2（話者分離・出力拡充）

| ID | タスク | 状態 |
|---|---|---|
| P2-1 | pyannote-audio 話者分離ラッパー（device自動・互換性パッチ込み） | 未着手 |
| P2-2 | 話者ラベル手動編集 UI | 未着手 |
| P2-3 | Word (.docx) 出力対応 | 未着手 |
| P2-4 | 面接・授業プロンプトテンプレート追加 | 未着手 |
| P2-5 | Mac mlx-whisper 転写経路の統合 | 未着手 |

## Phase 3（UX改善・展開）

| ID | タスク | 状態 |
|---|---|---|
| P3-1 | 進捗表示改善（pyannote ProgressHook、faster-whisper print_progress） | 未着手 |
| P3-2 | 設定の永続化 | 未着手 |
| P3-3 | セットアップスクリプト / ドキュメント整備（Mac / Win） | 未着手 |
| P3-4 | Light ティア (8GB) 向けモデル最適化 | 未着手 |
| P3-5 | チームメンバーへの展開 | 未着手 |
