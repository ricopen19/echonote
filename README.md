# Echonote

音声ファイルから構造化されたテキスト記録を生成するローカル完結型アプリケーション。

---

## Windows セットアップ（初回のみ）

### 1. Python 3.12 をインストール

[https://www.python.org/downloads/](https://www.python.org/downloads/) から最新の 3.12.x をダウンロードしてインストール。

**インストール時の注意**: 「Add Python to PATH」にチェックを入れること。

インストール後、コマンドプロンプト（`Win + R` → `cmd`）で確認：

```
python --version
```

`Python 3.12.x` と表示されれば OK。

---

### 2. uv をインストール

コマンドプロンプトで：

```
pip install uv
```

---

### 3. ffmpeg をインストール

[https://github.com/BtbN/FFmpeg-Builds/releases](https://github.com/BtbN/FFmpeg-Builds/releases) から `ffmpeg-master-latest-win64-gpl.zip` をダウンロード。

解凍して `bin` フォルダの中身（`ffmpeg.exe` など）を `C:\ffmpeg\bin\` に配置。

次に PATH を通す：
1. スタートメニューで「環境変数」と検索 → 「システム環境変数の編集」
2. 「環境変数」ボタン → システム変数の `Path` を選択 → 「編集」
3. 「新規」で `C:\ffmpeg\bin` を追加 → OK

コマンドプロンプトを**再起動**して確認：

```
ffmpeg -version
```

---

### 4. Ollama をインストール

[https://ollama.com/download](https://ollama.com/download) から Windows 版をダウンロードしてインストール。

インストール後、コマンドプロンプトで日本語用モデルをダウンロード（約 2.5GB）：

```
ollama pull qwen3:4b-q4_K_M
```

---

### 5. Echonote をセットアップ

コマンドプロンプトで：

```
git clone https://github.com/ricopen19/echonote.git
cd echonote
uv sync
```

---

## 起動方法

毎回の手順：

**ターミナル 1** — Ollama サーバーを起動（起動したままにする）：

```
ollama serve
```

**ターミナル 2** — Echonote を起動：

```
cd echonote
uv run echonote
```

ブラウザで `http://localhost:7860` が自動で開きます。

---

## 初回設定

1. ブラウザで「⚙️ 設定」タブを開く
2. **LLM エンドポイント URL** → `http://localhost:11434/v1`
3. **LLM モデル名** → `qwen3:4b-q4_K_M`
4. 「設定を適用」→「✅ LLM サーバーに接続できました」と表示されれば OK

---

## 使い方

1. 「📝 文字起こし」タブで音声ファイル（mp3, wav, m4a など）をアップロード
2. モデル `small`、言語 `ja` のまま「▶ 文字起こし開始」（初回はモデルダウンロードで数分かかります）
3. 文字起こし結果が出たら「📄 記録生成」タブへ
4. テンプレートを選んで「▶ 記録を生成」
5. 「📥 Markdown をダウンロード」で保存

---

## Mac セットアップ（開発者向け）

```bash
# mlx-whisper（Apple Silicon 最適化）を含めてインストール
uv sync --extra mac

# LLM サーバーを起動（別ターミナル）
# Ollama を使う場合:
ollama serve

# Echonote を起動
uv run echonote
```
