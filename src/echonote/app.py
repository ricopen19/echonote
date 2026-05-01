"""Gradio アプリ — エントリーポイント。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import gradio as gr

from echonote import config as cfg
from echonote import exporter, llm, transcriber

_SETTINGS = cfg.load_settings()
_PROMPTS_DIR = Path(__file__).parent / "prompts"

TEMPLATE_NAMES = {
    "会議議事録": "meeting",
}


def _load_prompt(name: str) -> str:
    path = _PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _build_prompt(template_text: str, segments: list[cfg.Settings]) -> str:
    transcript = exporter.segments_to_transcript(segments)
    return template_text.replace("{transcript}", transcript)


# ── Tab 1: 文字起こし ──────────────────────────────────────────────────────────

def _model_cached(model_size: str) -> bool:
    """faster-whisper モデルがローカルにキャッシュ済みか確認する。"""
    import glob
    import os
    cache = os.path.expanduser("~/.cache/huggingface/hub")
    pattern = f"{cache}/models--Systran--faster-whisper-{model_size}"
    return bool(glob.glob(pattern))


def _do_transcribe(audio_path, model_size, language):
    if audio_path is None:
        raise gr.Error("音声ファイルをアップロードしてください。")

    use_mlx = _SETTINGS.platform.value == "mac"
    if use_mlx:
        yield [], "⏳ モデルを読み込み中..."
    elif not _model_cached(model_size):
        yield [], f"⬇️ faster-whisper/{model_size} モデルをダウンロード中（初回のみ）..."
    else:
        yield [], "⏳ モデルを読み込み中..."

    segments: list[dict] = []
    try:
        for seg in transcriber.transcribe_stream(
            audio_path,
            model_size=model_size,
            language=language,
            settings=_SETTINGS,
        ):
            segments.append(seg)
            yield segments, exporter.segments_to_transcript(segments)
    except RuntimeError as e:
        raise gr.Error(str(e)) from e


# ── Tab 2: 記録生成 ───────────────────────────────────────────────────────────

def _on_template_change(template_label: str) -> str:
    name = TEMPLATE_NAMES.get(template_label, "meeting")
    return _load_prompt(name)


def _do_generate(segments, prompt_template, llm_url, llm_model):
    if not segments:
        raise gr.Error("先に文字起こしを実行してください。")

    prompt = _build_prompt(prompt_template, segments)

    output = ""
    try:
        for chunk in llm.complete(prompt, base_url=llm_url, model=llm_model, stream=True):
            output += chunk
            yield output
    except llm.LLMConnectionError as e:
        raise gr.Error(str(e)) from e
    except llm.LLMError as e:
        raise gr.Error(str(e)) from e


def _do_download_md(content: str):
    if not content:
        raise gr.Error("先に記録を生成してください。")
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w", encoding="utf-8") as tmp:
        tmp.write(content)
        return tmp.name


# ── UI 構築 ───────────────────────────────────────────────────────────────────

def build_ui() -> gr.Blocks:
    settings = _SETTINGS
    default_prompt = _load_prompt("meeting")

    with gr.Blocks(title="Echonote", fill_height=False) as demo:
        gr.Markdown("# Echonote 🎧\n音声ファイルから構造化テキスト記録を生成します。")

        segments_state = gr.State([])

        with gr.Tabs():
            # ── Tab 1 ──────────────────────────────────────────────────────
            with gr.TabItem("📝 文字起こし"):
                with gr.Row():
                    with gr.Column(scale=2):
                        audio_input = gr.File(
                            label="音声ファイル",
                            file_types=["audio"],
                            type="filepath",
                        )
                    with gr.Column(scale=1):
                        model_dd = gr.Dropdown(
                            label="Whisper モデル",
                            choices=transcriber.WHISPER_MODELS,
                            value=settings.default_whisper_model,
                        )
                        lang_dd = gr.Dropdown(
                            label="言語",
                            choices=["ja", "en", "auto"],
                            value=settings.effective_language(),
                        )

                transcribe_btn = gr.Button("▶ 文字起こし開始", variant="primary")
                transcript_box = gr.Textbox(
                    label="文字起こし結果",
                    lines=15,
                    interactive=False,
                    placeholder="文字起こし結果がここに表示されます",
                )

                transcribe_btn.click(
                    fn=_do_transcribe,
                    inputs=[audio_input, model_dd, lang_dd],
                    outputs=[segments_state, transcript_box],
                )

            # ── Tab 2 ──────────────────────────────────────────────────────
            with gr.TabItem("📄 記録生成"):
                with gr.Row():
                    template_dd = gr.Dropdown(
                        label="テンプレート",
                        choices=list(TEMPLATE_NAMES.keys()),
                        value="会議議事録",
                        scale=1,
                    )
                prompt_box = gr.Textbox(
                    label="プロンプト（編集可能）",
                    value=default_prompt,
                    lines=8,
                )
                generate_btn = gr.Button("▶ 記録を生成", variant="primary")
                preview_box = gr.Textbox(
                    label="生成結果プレビュー",
                    lines=20,
                    interactive=False,
                    placeholder="生成結果がここに表示されます",
                )
                download_btn = gr.Button("📥 Markdown をダウンロード")
                download_file = gr.File(label="ダウンロード", visible=False)

                template_dd.change(fn=_on_template_change, inputs=template_dd, outputs=prompt_box)

                llm_url_state = gr.State(settings.effective_llm_url())
                llm_model_state = gr.State(settings.effective_llm_model())

                generate_btn.click(
                    fn=_do_generate,
                    inputs=[segments_state, prompt_box, llm_url_state, llm_model_state],
                    outputs=preview_box,
                )

                def _download(content):
                    path = _do_download_md(content)
                    return gr.update(value=path, visible=True)

                download_btn.click(fn=_download, inputs=preview_box, outputs=download_file)

            # ── Tab 3 ──────────────────────────────────────────────────────
            with gr.TabItem("⚙️ 設定"):
                llm_url_input = gr.Textbox(
                    label="LLM エンドポイント URL",
                    value=settings.effective_llm_url(),
                )
                llm_model_input = gr.Textbox(
                    label="LLM モデル名",
                    value=settings.effective_llm_model(),
                )
                hf_token_input = gr.Textbox(
                    label="HuggingFace トークン（話者分離用）",
                    value=settings.effective_hf_token(),
                    type="password",
                )
                save_btn = gr.Button("設定を適用", variant="secondary")
                save_status = gr.Markdown("")

                def _apply_settings(url, model, token):
                    _SETTINGS.ui_overrides["llm_url"] = url
                    _SETTINGS.ui_overrides["llm_model"] = model
                    _SETTINGS.ui_overrides["hf_token"] = token
                    reachable = llm.check_endpoint(url)
                    status = "✅ LLM サーバーに接続できました。" if reachable else "⚠️ LLM サーバーに接続できません。"
                    return url, model, status

                save_btn.click(
                    fn=_apply_settings,
                    inputs=[llm_url_input, llm_model_input, hf_token_input],
                    outputs=[llm_url_state, llm_model_state, save_status],
                )

    return demo


def main():
    demo = build_ui()
    demo.launch()


if __name__ == "__main__":
    main()
