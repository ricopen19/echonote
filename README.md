# Echonote

音声ファイルから構造化されたテキスト記録を生成するローカル完結型アプリケーション。

---

## Windows セットアップ（初回のみ）

### ステップ 1 — ファイルを入手する

**方法 A: ZIP ダウンロード（推奨・git 不要）**

1. このページ右上の「Code」→「Download ZIP」をクリック
2. ダウンロードした ZIP を右クリック →「すべて展開」
3. 展開先のフォルダ（例: `C:\echonote`）を覚えておく

**方法 B: git clone（更新を `git pull` で管理したい場合）**

```powershell
git clone https://github.com/ricopen19/echonote.git
cd echonote
```

---

### ステップ 2 — `setup.bat` をダブルクリック

フォルダ内の `setup.bat` をダブルクリックします。

「このアプリがデバイスに変更を加えることを許可しますか？」と表示されたら **「はい」** をクリックしてください。

画面の指示に従うと Python・ffmpeg・Ollama・AI モデルが自動でインストールされます。

> **「Installing Ollama...」で数分以上止まった場合**  
> Ollama のインストール完了と同時に Ollama のウィンドウが開きますが、セットアップスクリプトがそのプロセスを待ち続けてハングすることがあります。  
> Ollama のウィンドウが開いたら `setup.bat` の PowerShell ウィンドウで **Ctrl+C** を押して中断し、`setup.bat` をもう一度ダブルクリックしてください。2回目は Ollama のインストールをスキップして先に進みます。

完了後、**PC を再起動**してください。

### ステップ 3 — 以降は `start.bat` をダブルクリック

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
