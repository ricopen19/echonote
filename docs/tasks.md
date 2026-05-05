# Echonote — タスク一覧

## Phase 1 MVP（Windows Standard ティア優先）

**目標**: 音声アップロード → faster-whisper 転写 → Ollama LLM 構造化 → Markdown 出力 → Gradio UI

### Claude Code 担当

- [x] T1: プラットフォーム・HWティア検出、設定管理 — `src/echonote/config.py`
- [x] T2: faster-whisper ラッパー（統一出力フォーマット） — `src/echonote/transcriber.py`
- [x] T3: OpenAI互換 LLM クライアント（到達性確認・ストリーミング） — `src/echonote/llm.py`
- [x] T4: Gradio UI（Tab構成・処理フロー接続） — `src/echonote/app.py`

### Antigravity 担当

- [x] A1: Markdown 整形出力 — `src/echonote/exporter.py`
- [x] A2: 会議議事録プロンプトテンプレート — `src/echonote/prompts/meeting.txt`
- [x] A3: transcriber ユニットテスト（faster-whisper モック） — `tests/test_transcriber.py`
- [x] A4: llm クライアントのユニットテスト（requests モック） — `tests/test_llm.py`
- [x] A5: exporter のユニットテスト — `tests/test_exporter.py`

---

## Phase 2（話者分離・出力拡充）

- [x] P2-1: pyannote-audio 話者分離ラッパー（device自動・互換性パッチ込み）
- [x] P2-2: 話者ラベル手動編集 UI
- [x] P2-3: Word (.docx) 出力対応
- [ ] P2-4: 面接・授業プロンプトテンプレート追加
- [x] P2-5: Mac mlx-whisper 転写経路の統合

---

## Phase 3（UX改善・展開）

- [ ] P3-1: 進捗表示改善（pyannote ProgressHook、faster-whisper print_progress）
- [ ] P3-2: 設定の永続化
- [x] P3-3: セットアップスクリプト / ドキュメント整備（Mac / Win）— `setup.bat` / `scripts/setup.ps1`
- [ ] P3-4: Light ティア (8GB) 向けモデル最適化
- [ ] P3-5: チームメンバーへの展開
- [ ] P3-6: Playwright によるブラウザ自動テスト（`example-skills:webapp-testing` で設定）
- [ ] P3-7: 長時間音声のチャンク分割（OOM 対策）

---

## Phase 4（トランスクリプト UX）

- [ ] P4-1: 話者フィルタ — 指定した話者の発言のみ抽出・表示
- [ ] P4-2: ワード検索 — 文字起こし結果内のキーワード検索とハイライト
- [ ] P4-3: 音声プレーヤー連動 — 再生中のセグメントをリアルタイムでハイライト（YouTube 字幕風）
