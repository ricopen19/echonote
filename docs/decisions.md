# Echonote — 設計判断の記録

---

## D1: LLM クライアントに requests を使用（openai SDK を使わない）

`openai` SDK は Ollama の `base_url` 変更で使えるが、依存を増やさず `requests` で実装した。
ストリーミング SSE のパースを自前で書く必要があるが、pyproject.toml に既存の依存で済む。

**却下**: openai SDK — 機能的に同等だが依存追加のコストが高い。

---

## D2: LLM 生成後に keep_alive=0 でモデルをアンロード

Windows 検証（i5-8500 16GB）で `medium` モデル + 長時間音声の転写中に OOM クラッシュを確認。
原因は `ollama serve` がモデルを RAM に保持し続けること。`keep_alive: 0` を API リクエストに追加することで生成完了後に即アンロードされ、転写・話者分離とメモリが重複しなくなる。

**トレードオフ**: 2回目の生成に 10〜30 秒の再ロード待ちが発生するが、1セッション1回のユースケースでは問題なし。

---

## D3: mlx-whisper の 404 は静かに faster-whisper へフォールバック

`mlx-community/whisper-small` など一部モデルが HuggingFace に存在しない（404）。
`RepositoryNotFoundError` は既知の問題なのでスタックトレースを出さずにフォールバックする。
予期しない例外（ネットワーク障害など）はスタックトレースを出力する。

---

## D4: setup.ps1 を英語のみで記述

Mac で作成した UTF-8 ファイルを Windows PowerShell 5.1 が Shift-JIS として読み込み、日本語文字列がパースエラーになることを確認。BOM 付き UTF-8 の出力手段がないため、.ps1 ファイルは ASCII のみとした。

**却下**: BOM 付き UTF-8 での保存 — Write ツールが BOM を付けられない。

---

## D5: 転写をセグメント単位でストリーミング表示

faster-whisper の `model.transcribe()` はジェネレーターを返す。
全セグメント完了まで UI が固まる問題（20秒音声で60秒以上待機）を解消するため、セグメント確定のたびに `yield` して UI をリアルタイム更新する方式にした。
