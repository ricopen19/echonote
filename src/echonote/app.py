"""Gradio アプリ — エントリーポイント。"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import gradio as gr

from echonote import config as cfg
from echonote import diarizer, exporter, llm, transcriber, trimmer

_SETTINGS = cfg.load_settings()
_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _fmt_sec(sec: int) -> str:
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _on_audio_upload(audio_path):
    if audio_path is None:
        return 0.0
    return trimmer.get_duration(audio_path)


def _update_trim_info(start, end, duration):
    if duration <= 0:
        return ""
    s, e, dur = float(start or 0), float(end or 0), float(duration)
    if s <= 0.5 and e >= dur - 0.5:
        return f"全体を転写（{_fmt_sec(int(dur))}）"
    return f"✂️ **{_fmt_sec(int(s))} 〜 {_fmt_sec(int(e))}**（{_fmt_sec(max(0, int(e - s)))} を転写）"


_WAVEFORM_HTML = """
<div id="echonote-player" style="background:#1e1e2e;border-radius:8px;padding:16px;margin:4px 0;user-select:none;">
  <div id="echonote-waveform" style="min-height:100px;cursor:col-resize;"></div>
  <div style="display:flex;align-items:center;gap:12px;margin-top:10px;">
    <button id="echonote-play-btn"
            onclick="if(window.echonoteWS)window.echonoteWS.playPause()"
            style="background:#4a9eff;color:#fff;border:none;border-radius:50%;width:40px;height:40px;cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">▶</button>
    <span id="echonote-time" style="font-family:monospace;color:#aaa;font-size:13px;flex-shrink:0;">0:00 / 0:00</span>
    <span id="echonote-region-info" style="margin-left:auto;color:#4a9eff;font-size:13px;font-weight:500;"></span>
  </div>
  <p style="color:#555;font-size:11px;margin:8px 0 0;text-align:center;">波形の端をドラッグしてトリム範囲を選択 · クリックで再生位置を移動</p>
</div>
"""

_HEAD_SCRIPT = """<script type="module">
// launch(js=) の実行保証が不明なため head= に script タグを直接注入
import WaveSurfer from 'https://cdn.jsdelivr.net/npm/wavesurfer.js@7/dist/wavesurfer.esm.js';
import RegionsPlugin from 'https://cdn.jsdelivr.net/npm/wavesurfer.js@7/dist/plugins/regions.esm.js';

function fmtSec(s) {
    s = Math.max(0, s);
    const m = Math.floor(s / 60), sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, '0')}`;
}

function setGradioNum(elemId, value) {
    const el = document.getElementById(elemId);
    if (!el) return;
    const input = el.querySelector('input[type="number"]');
    if (!input) return;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(input, String(value));
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
}

function initPlayer(url) {
    if (window.echonoteWS) { window.echonoteWS.destroy(); window.echonoteWS = null; }
    const container = document.getElementById('echonote-waveform');
    if (!container) { setTimeout(() => initPlayer(url), 200); return; }
    container.innerHTML = '';

    const regions = RegionsPlugin.create();
    const ws = window.echonoteWS = WaveSurfer.create({
        container,
        waveColor: '#4a9eff',
        progressColor: '#1a5eb5',
        height: 100,
        plugins: [regions],
    });
    ws.load(url);

    ws.on('ready', () => {
        const dur = ws.getDuration();
        regions.addRegion({
            start: 0, end: dur,
            color: 'rgba(74,158,255,0.2)',
            drag: true, resize: true,
        });
        const timeEl = document.getElementById('echonote-time');
        if (timeEl) timeEl.textContent = `0:00 / ${fmtSec(dur)}`;
        const infoEl = document.getElementById('echonote-region-info');
        if (infoEl) infoEl.textContent = '';
        setGradioNum('echonote-trim-start', 0);
        setGradioNum('echonote-trim-end', dur);
    });

    ws.on('timeupdate', (t) => {
        const timeEl = document.getElementById('echonote-time');
        if (timeEl) timeEl.textContent = `${fmtSec(t)} / ${fmtSec(ws.getDuration())}`;
        const btn = document.getElementById('echonote-play-btn');
        if (btn) btn.textContent = ws.isPlaying() ? '⏸' : '▶';
    });

    ws.on('finish', () => {
        const btn = document.getElementById('echonote-play-btn');
        if (btn) btn.textContent = '▶';
    });

    regions.on('region-updated', (region) => {
        setGradioNum('echonote-trim-start', region.start);
        setGradioNum('echonote-trim-end', region.end);
        const infoEl = document.getElementById('echonote-region-info');
        if (infoEl) infoEl.textContent = `✂️ ${fmtSec(region.start)} 〜 ${fmtSec(region.end)}`;
    });
}

// ファイル選択時に Object URL を生成 → サーバー URL 形式に依存しない
function _loadFile(file) {
    if (!file) return;
    if (window._echonoteObjUrl) URL.revokeObjectURL(window._echonoteObjUrl);
    window._echonoteObjUrl = URL.createObjectURL(file);
    initPlayer(window._echonoteObjUrl);
}

let watchedInput = null;
let dropWatched = false;
setInterval(() => {
    const container = document.getElementById('echonote-file-input');
    if (!container) return;

    // D&D: Gradio が Svelte で横取りするため change イベントが発火しない
    // → capture フェーズで drop を先取りして dataTransfer から File を取得
    if (!dropWatched) {
        dropWatched = true;
        container.addEventListener('drop', (e) => {
            const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
            _loadFile(file);
        }, true);
    }

    const fileInput = container.querySelector('input[type="file"]');
    if (!fileInput || fileInput === watchedInput) return;
    watchedInput = fileInput;
    fileInput.addEventListener('change', (e) => {
        _loadFile(e.target.files && e.target.files[0]);
    });
}, 500);
</script>"""

_INVALID_FNAME = re.compile(r'[/\\:*?"<>|\x00-\x1f]')


def _list_templates() -> list[str]:
    return sorted(p.stem for p in _PROMPTS_DIR.glob("*.txt"))


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


def _do_transcribe(audio_path, model_size, language, do_diarize, chunk_minutes_str, trim_start, trim_end):
    if audio_path is None:
        raise gr.Error("音声ファイルをアップロードしてください。")

    duration = trimmer.get_duration(audio_path)
    if trim_start > 0 or (duration > 0 and trim_end < duration - 1):
        audio_path = trimmer.trim(audio_path, trim_start, trim_end if trim_end > 0 else 0)

    chunk_minutes = int(chunk_minutes_str.replace("分", ""))
    llm.try_unload(_SETTINGS.effective_llm_url(), _SETTINGS.effective_llm_model())

    use_mlx = _SETTINGS.platform.value == "mac"
    if use_mlx:
        init_status = "⏳ モデルを読み込み中..."
    elif not _model_cached(model_size):
        init_status = f"⬇️ faster-whisper/{model_size} モデルをダウンロード中（初回のみ）..."
    else:
        init_status = "⏳ モデルを読み込み中..."

    yield [], "", gr.update(visible=False), gr.update(visible=False), init_status

    status = {"text": "🔄 文字起こし中..."}

    def on_chunk(idx: int, total: int, start_min: float, end_min: float) -> None:
        if total == 1:
            status["text"] = "🔄 文字起こし中..."
        else:
            status["text"] = (
                f"🔄 チャンク {idx + 1} / {total} 処理中"
                f"（{start_min:.0f}〜{end_min:.0f} 分）"
            )

    segments: list[dict] = []
    try:
        for seg in transcriber.transcribe_stream(
            audio_path,
            model_size=model_size,
            language=language,
            settings=_SETTINGS,
            on_chunk=on_chunk,
            chunk_minutes=chunk_minutes,
        ):
            segments.append(seg)
            yield (
                segments,
                exporter.segments_to_transcript(segments),
                gr.update(visible=False),
                gr.update(visible=False),
                status["text"],
            )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise gr.Error(f"{type(e).__name__}: {e}") from e

    if not do_diarize:
        done = f"✅ 文字起こし完了（{len(segments)} セグメント）"
        yield segments, exporter.segments_to_transcript(segments), gr.update(visible=False), gr.update(visible=False), done
        return

    diarize_status = "⏳ 話者分離中（数分かかります）..."
    yield segments, exporter.segments_to_transcript(segments), gr.update(visible=False), gr.update(visible=False), diarize_status
    try:
        segments = diarizer.diarize(audio_path, _SETTINGS.effective_hf_token(), segments)
    except (ValueError, ImportError) as e:
        raise gr.Error(str(e)) from e
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise gr.Error(f"話者分離エラー: {type(e).__name__}: {e}") from e

    speakers = sorted({s.get("speaker", "") for s in segments if s.get("speaker")})
    df_data = [[spk, ""] for spk in speakers]
    done = f"✅ 文字起こし + 話者分離完了（{len(segments)} セグメント）"
    yield (
        segments,
        exporter.segments_to_transcript(segments),
        gr.update(value=df_data, visible=True),
        gr.update(visible=True),
        done,
    )


def _do_apply_speakers(segments: list[dict], df):
    rows = df.values.tolist() if hasattr(df, "values") else (df or [])
    mapping = {
        str(row[0]): str(row[1]).strip()
        for row in rows
        if len(row) >= 2 and row[0] and str(row[1]).strip()
    }
    updated = [
        {**seg, "speaker": mapping.get(seg.get("speaker", ""), seg.get("speaker", ""))}
        for seg in segments
    ]
    return updated, exporter.segments_to_transcript(updated)


# ── セクション検出ヘルパー ───────────────────────────────────────────────────────

def _section_text(section_segments: list[dict]) -> str:
    lines = []
    for s in section_segments:
        speaker = s.get("speaker", "")
        prefix = f"{speaker}: " if speaker else ""
        lines.append(f"{prefix}{s['text'].strip()}")
    return "\n".join(lines)


_SHOW: list[str] = []
_HIDE: list[str] = ["echonote-hidden"]


def _build_section_ui(sections: list, page: int) -> tuple:
    """nav_outputs (16 要素) に対応するタプルを返す。
    visible トグルの代わりに elem_classes で表示制御し Gradio 6 の DOM 再挿入バグを回避する。
    """
    n = len(sections)
    if n == 0:
        return (
            0,
            gr.update(value=""),
            gr.update(value="", visible=False),
            gr.update(elem_classes=_HIDE),           # copy_btn
            *[gr.update(elem_classes=_HIDE) for _ in range(7)],
            gr.update(elem_classes=_HIDE),           # prev
            gr.update(elem_classes=_HIDE),           # next
            gr.update(value=""),                     # display
            gr.update(elem_classes=_HIDE),           # jump_input
            gr.update(elem_classes=_HIDE),           # jump_btn
        )
    page = max(0, min(page, n - 1))
    text = _section_text(sections[page])
    header = f"**セクション {page + 1} / {n}**"
    if n <= 7:
        btn_updates = [
            gr.update(
                value=str(i + 1), elem_classes=_SHOW,
                variant="primary" if i == page else "secondary",
            ) if i < n else gr.update(elem_classes=_HIDE)
            for i in range(7)
        ]
        return (
            page,
            gr.update(value=header),
            gr.update(value=text, visible=True),
            gr.update(elem_classes=_SHOW),           # copy_btn
            *btn_updates,
            gr.update(elem_classes=_HIDE),           # prev
            gr.update(elem_classes=_HIDE),           # next
            gr.update(value=""),                     # display
            gr.update(elem_classes=_HIDE),           # jump_input
            gr.update(elem_classes=_HIDE),           # jump_btn
        )
    return (
        page,
        gr.update(value=header),
        gr.update(value=text, visible=True),
        gr.update(elem_classes=_SHOW),               # copy_btn
        *[gr.update(elem_classes=_HIDE) for _ in range(7)],
        gr.update(elem_classes=_SHOW),               # prev
        gr.update(elem_classes=_SHOW),               # next
        gr.update(value=f"{page + 1} / {n}"),        # display
        gr.update(elem_classes=_SHOW),               # jump_input
        gr.update(elem_classes=_SHOW),               # jump_btn
    )


def _do_detect_sections(segments, gap_sec):
    if not segments:
        raise gr.Error("先に文字起こしを実行してください。")
    sections = exporter.split_by_gap(segments, float(gap_sec))
    return (sections,) + _build_section_ui(sections, 0)


def _nav_prev(sections, page):
    return _build_section_ui(sections, max(0, int(page) - 1))


def _nav_next(sections, page):
    return _build_section_ui(sections, min(len(sections) - 1, int(page) + 1))


def _nav_jump(sections, jump_val):
    n = len(sections)
    page = max(0, min(int(jump_val or 1) - 1, n - 1))
    return _build_section_ui(sections, page)


def _make_nav_page(idx: int):
    def _fn(sections):
        return _build_section_ui(sections, idx)
    return _fn


# ── Tab 2: 記録生成 ───────────────────────────────────────────────────────────

def _on_template_change(template_label: str) -> str:
    return _load_prompt(template_label)


def _do_save_overwrite(name: str, content: str) -> str:
    if not name:
        return "⚠️ テンプレートが選択されていません。"
    (_PROMPTS_DIR / f"{name}.txt").write_text(content, encoding="utf-8")
    return f"✅ 「{name}」を保存しました。"


def _do_create_template(new_name: str, content: str):
    new_name = new_name.strip()
    if not new_name:
        return gr.update(), gr.update(), "⚠️ テンプレート名を入力してください。"
    if _INVALID_FNAME.search(new_name):
        return gr.update(), gr.update(), "⚠️ テンプレート名に使えない文字が含まれています。"
    if (_PROMPTS_DIR / f"{new_name}.txt").exists():
        return gr.update(), gr.update(), f"⚠️「{new_name}」は既に存在します。"
    (_PROMPTS_DIR / f"{new_name}.txt").write_text(content, encoding="utf-8")
    choices = _list_templates()
    return gr.update(choices=choices, value=new_name), "", f"✅ 「{new_name}」を作成しました。"


def _do_delete_template(name: str):
    if not name:
        return gr.update(), gr.update(), "⚠️ テンプレートが選択されていません。"
    if len(_list_templates()) <= 1:
        return gr.update(), gr.update(), "⚠️ 最後のテンプレートは削除できません。"
    (_PROMPTS_DIR / f"{name}.txt").unlink(missing_ok=True)
    remaining = _list_templates()
    new_val = remaining[0] if remaining else ""
    return (
        gr.update(choices=remaining, value=new_val),
        gr.update(value=_load_prompt(new_val) if new_val else ""),
        f"🗑️ 「{name}」を削除しました。",
    )


def _do_generate(segments, prompt_template, llm_url, llm_model):
    import gc
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
    finally:
        gc.collect()


def _do_download_md(content: str):
    if not content:
        raise gr.Error("先に記録を生成してください。")
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w", encoding="utf-8") as tmp:
        tmp.write(content)
        return tmp.name


def _do_download_docx(content: str):
    if not content:
        raise gr.Error("先に記録を生成してください。")
    data = exporter.to_docx(content)
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False, mode="wb") as tmp:
        tmp.write(data)
        return tmp.name


# ── UI 構築 ───────────────────────────────────────────────────────────────────

def build_ui() -> gr.Blocks:
    settings = _SETTINGS
    _tpls = _list_templates()
    default_prompt = _load_prompt(_tpls[0]) if _tpls else ""

    with gr.Blocks(title="Echonote", fill_height=False) as demo:
        gr.Markdown("# Echonote 🎧\n音声ファイルから構造化テキスト記録を生成します。")

        segments_state = gr.State([])

        with gr.Tabs():
            # ── Tab 1 ──────────────────────────────────────────────────────
            with gr.TabItem("📝 文字起こし"):
                duration_state = gr.State(0.0)

                with gr.Row():
                    with gr.Column(scale=2):
                        audio_input = gr.File(
                            label="音声ファイル",
                            file_types=["audio"],
                            type="filepath",
                            elem_id="echonote-file-input",
                        )
                        gr.HTML(_WAVEFORM_HTML)
                        # trim 値を JS → Python に渡す（CSS 非表示 — visible=False だと DOM から消える）
                        trim_start_num = gr.Number(
                            value=0.0, visible=True,
                            elem_id="echonote-trim-start",
                            elem_classes=["echonote-hidden"],
                            label="trim_start",
                        )
                        trim_end_num = gr.Number(
                            value=0.0, visible=True,
                            elem_id="echonote-trim-end",
                            elem_classes=["echonote-hidden"],
                            label="trim_end",
                        )
                        trim_info_md = gr.Markdown("")
                    with gr.Column(scale=1):
                        model_dd = gr.Dropdown(
                            label="Whisper モデル",
                            choices=transcriber.WHISPER_MODELS,
                            value="small",
                        )
                        lang_dd = gr.Dropdown(
                            label="言語",
                            choices=["ja", "en", "auto"],
                            value=settings.effective_language(),
                        )
                        diarize_chk = gr.Checkbox(
                            label="話者分離を実行（HF トークン必須）",
                            value=False,
                        )
                        chunk_dd = gr.Dropdown(
                            label="チャンク分割（長音声OOM対策）",
                            choices=["3分", "5分", "10分"],
                            value="5分",
                        )

                transcribe_btn = gr.Button("▶ 文字起こし開始", variant="primary")
                status_md = gr.Markdown("")
                transcript_box = gr.Textbox(
                    label="文字起こし結果",
                    lines=15,
                    interactive=False,
                    placeholder="文字起こし結果がここに表示されます",
                    elem_id="echonote-transcript",
                )
                copy_no_ts_btn = gr.Button(
                    "📋 タイムスタンプなしでコピー", size="sm", variant="secondary",
                )

                speakers_df = gr.Dataframe(
                    headers=["話者", "名前"],
                    datatype=["str", "str"],
                    label="話者リネーム（名前を入力して「適用」）",
                    interactive=True,
                    visible=False,
                )
                apply_speakers_btn = gr.Button("話者名を適用", visible=False)

                gr.Markdown("---")
                sections_state = gr.State([])
                sec_page_state = gr.State(0)

                with gr.Row():
                    gap_slider = gr.Slider(
                        label="無音ギャップ閾値（秒）",
                        minimum=2, maximum=30, value=5, step=1,
                        scale=3,
                    )
                    detect_btn = gr.Button("🔍 セクションを検出", scale=1, variant="secondary")

                with gr.Row():
                    section_header_md = gr.Markdown("")
                    copy_section_btn = gr.Button(
                        "📋 コピー", size="sm", variant="secondary",
                        visible=True, elem_classes=["echonote-hidden"], scale=0,
                    )

                with gr.Row():
                    num_btns = [
                        gr.Button(
                            str(i + 1), size="sm", variant="secondary",
                            visible=True, elem_classes=["echonote-hidden"], min_width=40, scale=0,
                        )
                        for i in range(7)
                    ]
                    prev_btn_sec = gr.Button(
                        "◀", size="sm", visible=True, elem_classes=["echonote-hidden"], min_width=40, scale=0,
                    )
                    page_display_md = gr.Markdown("")
                    next_btn_sec = gr.Button(
                        "▶", size="sm", visible=True, elem_classes=["echonote-hidden"], min_width=40, scale=0,
                    )

                with gr.Row():
                    jump_input = gr.Number(
                        label="ページ番号", minimum=1, value=1, step=1,
                        visible=True, elem_classes=["echonote-hidden"], scale=1, precision=0,
                    )
                    jump_btn = gr.Button(
                        "移動", size="sm", visible=True, elem_classes=["echonote-hidden"], scale=0,
                    )

                section_text_box = gr.Textbox(
                    label="セクション内容",
                    lines=10,
                    interactive=False,
                    visible=False,
                    elem_id="echonote-section-text",
                )

                audio_input.change(
                    fn=_on_audio_upload,
                    inputs=[audio_input],
                    outputs=[duration_state],
                )
                trim_start_num.change(
                    fn=_update_trim_info,
                    inputs=[trim_start_num, trim_end_num, duration_state],
                    outputs=trim_info_md,
                )
                trim_end_num.change(
                    fn=_update_trim_info,
                    inputs=[trim_start_num, trim_end_num, duration_state],
                    outputs=trim_info_md,
                )
                transcribe_btn.click(
                    fn=_do_transcribe,
                    inputs=[audio_input, model_dd, lang_dd, diarize_chk, chunk_dd, trim_start_num, trim_end_num],
                    outputs=[segments_state, transcript_box, speakers_df, apply_speakers_btn, status_md],
                )
                apply_speakers_btn.click(
                    fn=_do_apply_speakers,
                    inputs=[segments_state, speakers_df],
                    outputs=[segments_state, transcript_box],
                )
                copy_no_ts_btn.click(
                    fn=None,
                    js="""() => {
                        const ta = document.querySelector('#echonote-transcript textarea');
                        if (!ta || !ta.value) return;
                        const text = ta.value
                            .split('\\n')
                            .map(l => l.replace(/^\\[\\d+:\\d{2} - \\d+:\\d{2}\\] /, ''))
                            .join('\\n');
                        navigator.clipboard.writeText(text).catch(() => {});
                    }""",
                )

                copy_section_btn.click(
                    fn=None,
                    js="""() => {
                        const ta = document.querySelector('#echonote-section-text textarea');
                        if (ta) navigator.clipboard.writeText(ta.value).catch(() => {});
                    }""",
                )
                nav_outputs = [
                    sec_page_state, section_header_md, section_text_box, copy_section_btn,
                    *num_btns, prev_btn_sec, next_btn_sec, page_display_md,
                    jump_input, jump_btn,
                ]
                detect_btn.click(
                    fn=_do_detect_sections,
                    inputs=[segments_state, gap_slider],
                    outputs=[sections_state] + nav_outputs,
                )
                prev_btn_sec.click(
                    fn=_nav_prev,
                    inputs=[sections_state, sec_page_state],
                    outputs=nav_outputs,
                )
                next_btn_sec.click(
                    fn=_nav_next,
                    inputs=[sections_state, sec_page_state],
                    outputs=nav_outputs,
                )
                jump_btn.click(
                    fn=_nav_jump,
                    inputs=[sections_state, jump_input],
                    outputs=nav_outputs,
                )
                for i, _nb in enumerate(num_btns):
                    _nb.click(
                        fn=_make_nav_page(i),
                        inputs=[sections_state],
                        outputs=nav_outputs,
                    )

            # ── Tab 2 ──────────────────────────────────────────────────────
            with gr.TabItem("📄 記録生成"):
                with gr.Row():
                    template_dd = gr.Dropdown(
                        label="テンプレート",
                        choices=_tpls,
                        value=_tpls[0] if _tpls else None,
                        scale=2,
                    )
                    save_tpl_btn = gr.Button("💾 上書き保存", scale=0, size="sm", variant="secondary")
                    del_tpl_btn = gr.Button("🗑️ 削除", scale=0, size="sm", variant="stop")
                with gr.Row():
                    new_tpl_name = gr.Textbox(
                        label="新規テンプレート名", placeholder="例：面接メモ", scale=2,
                    )
                    new_tpl_btn = gr.Button("➕ 新規保存", scale=0, size="sm", variant="secondary")
                tpl_status_md = gr.Markdown("")
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
                with gr.Row():
                    download_md_btn = gr.Button("📥 Markdown をダウンロード")
                    download_docx_btn = gr.Button("📥 Word をダウンロード")
                download_file = gr.File(label="ダウンロード", visible=False)

                template_dd.change(fn=_on_template_change, inputs=template_dd, outputs=prompt_box)
                save_tpl_btn.click(
                    fn=_do_save_overwrite,
                    inputs=[template_dd, prompt_box],
                    outputs=tpl_status_md,
                )
                new_tpl_btn.click(
                    fn=_do_create_template,
                    inputs=[new_tpl_name, prompt_box],
                    outputs=[template_dd, new_tpl_name, tpl_status_md],
                )
                del_tpl_btn.click(
                    fn=_do_delete_template,
                    inputs=[template_dd],
                    outputs=[template_dd, prompt_box, tpl_status_md],
                )

                llm_url_state = gr.State(settings.effective_llm_url())
                llm_model_state = gr.State(settings.effective_llm_model())

                generate_btn.click(
                    fn=_do_generate,
                    inputs=[segments_state, prompt_box, llm_url_state, llm_model_state],
                    outputs=preview_box,
                )

                def _download_md(content):
                    path = _do_download_md(content)
                    return gr.update(value=path, visible=True)

                def _download_docx(content):
                    path = _do_download_docx(content)
                    return gr.update(value=path, visible=True)

                download_md_btn.click(fn=_download_md, inputs=preview_box, outputs=download_file)
                download_docx_btn.click(fn=_download_docx, inputs=preview_box, outputs=download_file)

            # ── Tab 3 ──────────────────────────────────────────────────────
            with gr.TabItem("⚙️ 設定"):
                _PRESET_URLS = {
                    "Ollama (localhost:11434)": "http://localhost:11434/v1",
                    "mlx-lm (localhost:8080)": "http://localhost:8080/v1",
                }
                _current_url = settings.effective_llm_url()
                _preset_label = next(
                    (k for k, v in _PRESET_URLS.items() if v == _current_url),
                    list(_PRESET_URLS.keys())[0],
                )

                endpoint_radio = gr.Radio(
                    label="LLM エンドポイント",
                    choices=list(_PRESET_URLS.keys()),
                    value=_preset_label,
                )
                llm_url_input = gr.Textbox(
                    label="エンドポイント URL（直接編集可）",
                    value=_current_url,
                )
                with gr.Row():
                    llm_model_input = gr.Dropdown(
                        label="LLM モデル名",
                        choices=[settings.effective_llm_model()],
                        value=settings.effective_llm_model(),
                        allow_custom_value=True,
                    )
                    fetch_models_btn = gr.Button("一覧を取得", scale=0, size="sm")
                hf_token_input = gr.Textbox(
                    label="HuggingFace トークン（話者分離用）",
                    value=settings.effective_hf_token(),
                    type="password",
                )
                save_btn = gr.Button("設定を適用", variant="secondary")
                save_status = gr.Markdown("")

                def _on_endpoint_radio(choice):
                    preset = {
                        "Ollama (localhost:11434)": "http://localhost:11434/v1",
                        "mlx-lm (localhost:8080)": "http://localhost:8080/v1",
                    }
                    return preset.get(choice, "")

                def _fetch_models(url):
                    try:
                        import requests as _req
                        host = url.rstrip("/")
                        if host.endswith("/v1"):
                            host = host[:-3]
                        resp = _req.get(f"{host}/api/tags", timeout=5)
                        if resp.status_code == 200:
                            models = [m["name"] for m in resp.json().get("models", [])]
                            if models:
                                return gr.update(choices=models), "✅ モデル一覧を取得しました。"
                    except Exception:
                        pass
                    return gr.update(), "⚠️ モデル一覧の取得に失敗しました。"

                def _apply_settings(url, model, token):
                    _SETTINGS.ui_overrides["llm_url"] = url
                    _SETTINGS.ui_overrides["llm_model"] = model
                    _SETTINGS.ui_overrides["hf_token"] = token
                    reachable = llm.check_endpoint(url)
                    status = "✅ LLM サーバーに接続できました。" if reachable else "⚠️ LLM サーバーに接続できません。"
                    return url, model, status

                endpoint_radio.change(
                    fn=_on_endpoint_radio,
                    inputs=endpoint_radio,
                    outputs=llm_url_input,
                )
                fetch_models_btn.click(
                    fn=_fetch_models,
                    inputs=llm_url_input,
                    outputs=[llm_model_input, save_status],
                )
                save_btn.click(
                    fn=_apply_settings,
                    inputs=[llm_url_input, llm_model_input, hf_token_input],
                    outputs=[llm_url_state, llm_model_state, save_status],
                )

    return demo


_HIDE_CSS = ".echonote-hidden { display: none !important; }"


def main():
    demo = build_ui()
    demo.launch(head=_HEAD_SCRIPT, css=_HIDE_CSS)


if __name__ == "__main__":
    main()
