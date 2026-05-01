# Echonote

音声ファイルから構造化されたテキスト記録を生成するローカル完結型アプリケーション。

---

## Windows セットアップ（初回のみ）

### ステップ 1 — セットアップスクリプトを実行

PowerShell を**管理者として**起動（スタートメニューで「PowerShell」を右クリック → 管理者として実行）し、以下を実行：

```powershell
cd C:\path\to\echonote    # echonote フォルダの場所に合わせて変更
.\scripts\setup.ps1
```

画面の指示に従うと Python・ffmpeg・Ollama・AI モデルが自動でインストールされます。

完了後、**PC を再起動**してください。

### ステップ 2 — 以降は start.bat をダブルクリック

`start.bat` をダブルクリックするとブラウザが開きます。

---

## 使い方

1. 「📝 文字起こし」タブで音声ファイル（mp3, wav, m4a など）をアップロード
2. 「▶ 文字起こし開始」をクリック（**初回はモデルのダウンロードで数分かかります**）
3. 文字起こし結果が出たら「📄 記録生成」タブへ
4. テンプレートを選んで「▶ 記録を生成」
5. 「📥 Markdown をダウンロード」で保存

### 初回設定（設定タブ）

| 項目 | 値 |
|---|---|
| LLM エンドポイント URL | `http://localhost:11434/v1` |
| LLM モデル名 | `qwen3:4b-q4_K_M` |

---

## Mac セットアップ（開発者向け）

```bash
# mlx-whisper（Apple Silicon 最適化）を含めてインストール
uv sync --extra mac

# LLM サーバーを起動（別ターミナル）
ollama serve

# Echonote を起動
uv run echonote
```
