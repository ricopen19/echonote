# /// script
# requires-python = ">=3.10"
# dependencies = ["fastapi", "uvicorn[standard]"]
# ///
"""echonote Theme Studio

使い方:
    uv run --script echonote-ui-mockup/theme-studio.py

右パネルに実際のアプリ (localhost:5173) を表示し、
カラーピッカー操作が postMessage でリアルタイム反映される。
Save で index.css に書き戻し → Vite HMR が自動反映。
"""
from __future__ import annotations

import re
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

INDEX_CSS = Path(__file__).parent / "src" / "index.css"
PORT = 7777

app = FastAPI()


def parse_css(css_text: str) -> tuple[dict[str, str], dict[str, str]]:
    def extract(block: str) -> dict[str, str]:
        return {
            m.group(1): m.group(2).strip()
            for m in re.finditer(r"--([a-z-]+):\s*([^;]+);", block)
        }
    root_m = re.search(r":root\s*\{([^}]+)\}", css_text, re.DOTALL)
    dark_m = re.search(r"\.dark\s*\{([^}]+)\}", css_text, re.DOTALL)
    return (
        extract(root_m.group(1)) if root_m else {},
        extract(dark_m.group(1)) if dark_m else {},
    )


def write_css(light: dict[str, str], dark: dict[str, str]) -> None:
    css = INDEX_CSS.read_text()

    def replace_block(css_text: str, vars: dict[str, str], pattern: str) -> str:
        m = re.search(pattern, css_text, re.DOTALL)
        if not m:
            return css_text
        def replace_var(vm: re.Match) -> str:
            val = vars.get(vm.group(1))
            return f"--{vm.group(1)}: {val};" if val is not None else vm.group(0)
        updated = re.sub(r"--([a-z-]+):[^;]+;", replace_var, m.group(2))
        return css_text[: m.start(2)] + updated + css_text[m.end(2):]

    css = replace_block(css, light, r"(:root\s*\{)([^}]+)(\})")
    css = replace_block(css, dark,  r"(\.dark\s*\{)([^}]+)(\})")
    INDEX_CSS.write_text(css)


class ThemePayload(BaseModel):
    light: dict[str, str]
    dark: dict[str, str]


@app.get("/api/theme")
def get_theme() -> dict:
    light, dark = parse_css(INDEX_CSS.read_text())
    return {"light": light, "dark": dark}


@app.post("/api/theme")
def save_theme(payload: ThemePayload) -> dict:
    write_css(payload.light, payload.dark)
    return {"ok": True}


HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>echonote Theme Studio</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #111; color: #ddd; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }

/* ── Header ── */
header { background: #1a1a1a; border-bottom: 1px solid #2a2a2a;
         padding: 10px 16px; display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.app-title { font-size: 14px; font-weight: 600; color: #fff; }
.app-sub { font-size: 11px; color: #555; }
.mode-toggle { display: flex; background: #111; border: 1px solid #2a2a2a;
               border-radius: 6px; overflow: hidden; margin-left: auto; }
.mode-btn { padding: 4px 14px; font-size: 12px; border: none; background: transparent;
            color: #666; cursor: pointer; transition: all 0.12s; }
.mode-btn.active { background: #252525; color: #ddd; }

/* ── Layout ── */
.main { display: flex; flex: 1; overflow: hidden; }

/* ── Sidebar ── */
.sidebar { width: 280px; background: #161616; border-right: 1px solid #222;
           display: flex; flex-direction: column; flex-shrink: 0; overflow: hidden; }

.sidebar-top { padding: 10px 12px; border-bottom: 1px solid #222; display: flex; flex-direction: column; gap: 7px; }

.url-row { display: flex; align-items: center; gap: 6px; }
.url-label { font-size: 10px; color: #555; width: 28px; flex-shrink: 0; }
.url-input { flex: 1; background: #111; border: 1px solid #2a2a2a; color: #bbb;
             padding: 4px 8px; border-radius: 5px; font-size: 11px; font-family: monospace; outline: none; }
.url-input:focus { border-color: #444; }
.url-btn { background: #2a2a2a; border: none; color: #888; padding: 4px 10px;
           border-radius: 5px; font-size: 11px; cursor: pointer; white-space: nowrap; }
.url-btn:hover { background: #333; color: #bbb; }

.nav-chips { display: flex; flex-wrap: wrap; gap: 5px; }
.nav-chip { background: #1e1e1e; border: 1px solid #2a2a2a; color: #888;
            padding: 3px 10px; border-radius: 5px; font-size: 11px; cursor: pointer; transition: all 0.1s; }
.nav-chip:hover { border-color: #444; color: #bbb; }

.sidebar-scroll { flex: 1; overflow-y: auto; }
.sidebar-scroll::-webkit-scrollbar { width: 3px; }
.sidebar-scroll::-webkit-scrollbar-thumb { background: #2a2a2a; border-radius: 2px; }

/* Sections */
.sec { border-bottom: 1px solid #1e1e1e; }
.sec-hd { padding: 8px 14px; font-size: 11px; font-weight: 600; color: #555;
          text-transform: uppercase; letter-spacing: 0.08em; cursor: pointer;
          display: flex; align-items: center; justify-content: space-between;
          user-select: none; }
.sec-hd:hover { color: #888; }
.sec-hd .arrow { font-size: 9px; transition: transform 0.15s; }
.sec-hd.open .arrow { transform: rotate(180deg); }
.sec-body { display: none; padding-bottom: 4px; }
.sec-body.open { display: block; }

.color-row { display: flex; align-items: center; padding: 5px 14px; gap: 10px; cursor: default; }
.color-row:hover { background: #1c1c1c; }
.color-row.flashing { background: #1e1a10; }
.swatch { width: 20px; height: 20px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.07);
          flex-shrink: 0; position: relative; overflow: hidden; cursor: pointer; }
.swatch input[type=color] { position: absolute; inset: -6px; width: calc(100%+12px);
                             height: calc(100%+12px); border: none; padding: 0;
                             cursor: pointer; opacity: 0; }
.color-lbl-wrap { flex: 1; min-width: 0; }
.color-lbl { font-size: 12px; color: #aaa; display: block; }
.color-usage { font-size: 10px; color: #3b82f6; display: none; margin-top: 1px; }
.color-row:hover .color-usage { display: block; }
.color-hex { font-size: 10px; color: #555; font-family: monospace; flex-shrink: 0; }

.radius-wrap { padding: 8px 14px 10px; }
.radius-lbl { font-size: 12px; color: #aaa; display: flex; justify-content: space-between; margin-bottom: 6px; }
.radius-lbl span { color: #666; font-family: monospace; font-size: 11px; }
input[type=range] { width: 100%; accent-color: #3b82f6; cursor: pointer; }

/* ── Bottom bar ── */
.bottom-bar { padding: 10px 14px; border-top: 1px solid #222; background: #161616;
              display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.btn-back { background: transparent; color: #666; border: 1px solid #2a2a2a; padding: 6px 14px;
            border-radius: 6px; font-size: 12px; cursor: pointer; }
.btn-back:hover { border-color: #444; color: #aaa; }
.btn-reset { background: transparent; color: #666; border: 1px solid #2a2a2a; padding: 6px 14px;
             border-radius: 6px; font-size: 12px; cursor: pointer; }
.btn-reset:hover { border-color: #444; color: #aaa; }
.btn-save { background: #2563eb; color: #fff; border: none; padding: 6px 20px;
            border-radius: 6px; font-size: 12px; font-weight: 500; cursor: pointer;
            transition: background 0.15s; margin-left: auto; }
.btn-save:hover { background: #1d4ed8; }
.btn-save.saved { background: #16a34a !important; }
.dirty-dot { width: 6px; height: 6px; border-radius: 50%; background: #f59e0b;
             display: none; flex-shrink: 0; }
.dirty-dot.show { display: block; }
.inspector-btn { background: transparent; color: #555; border: 1px solid #2a2a2a;
                 padding: 5px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; }
.inspector-btn:hover { border-color: #444; color: #aaa; }
.inspector-btn.active { background: #1e3a5f; border-color: #3b82f6; color: #60a5fa; }
.color-row.inspected { background: #0f1e35 !important; outline: 1px solid #3b82f6; border-radius: 2px; }
.color-row.inspected .color-lbl { color: #60a5fa; }

/* ── Preview panel ── */
.preview-area { flex: 1; overflow: hidden; display: flex; flex-direction: column;
                background: #0a0a0a; }

.preview-toolbar { padding: 8px 14px; border-bottom: 1px solid #1e1e1e;
                   display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.preview-url { font-size: 11px; color: #555; font-family: monospace; }
.preview-reload { background: #1e1e1e; border: 1px solid #2a2a2a; color: #666;
                  padding: 3px 10px; border-radius: 4px; font-size: 11px; cursor: pointer; margin-left: auto; }
.preview-reload:hover { color: #aaa; }

.browser-chrome { background: #1e1e1e; border-bottom: 1px solid #2a2a2a;
                  padding: 6px 12px; display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.browser-dots { display: flex; gap: 5px; }
.browser-dot { width: 10px; height: 10px; border-radius: 50%; }
.browser-dot.red { background: #ff5f57; }
.browser-dot.yellow { background: #febc2e; }
.browser-dot.green { background: #28c840; }
.browser-addr { background: #111; border: 1px solid #2a2a2a; color: #888;
                padding: 3px 10px; border-radius: 4px; font-size: 11px; font-family: monospace;
                flex: 1; text-align: center; }

.iframe-wrap { flex: 1; position: relative; overflow: hidden; }
.iframe-wrap iframe { width: 100%; height: 100%; border: none; background: #fff; }

.no-app { display: flex; flex-direction: column; align-items: center; justify-content: center;
          height: 100%; gap: 12px; color: #444; }
.no-app p { font-size: 13px; }
.no-app code { font-size: 12px; background: #1a1a1a; padding: 4px 10px; border-radius: 4px;
               color: #666; font-family: monospace; }
</style>
</head>
<body>
<header>
  <div>
    <div class="app-title">echonote Theme Studio</div>
    <div class="app-sub">本アプリをライブ編集。Saveでこちらに保存→反映します。</div>
  </div>
  <button class="inspector-btn" id="inspector-btn" onclick="toggleInspector()" title="クリックした要素のCSS変数をサイドバーでハイライト">
    ◎ 要素を選択
  </button>
  <div class="mode-toggle">
    <button class="mode-btn active" onclick="setMode('light')">Light</button>
    <button class="mode-btn" onclick="setMode('dark')">Dark</button>
  </div>
</header>

<div class="main">
  <!-- Sidebar -->
  <div class="sidebar">
    <div class="sidebar-top">
      <div class="url-row">
        <span class="url-label">URL</span>
        <input class="url-input" id="app-url" value="http://localhost:5173" placeholder="http://localhost:5173">
        <button class="url-btn" onclick="loadApp()">接続</button>
      </div>
      <div class="nav-chips">
        <button class="nav-chip" onclick="navTo('/')">文字起こし</button>
        <button class="nav-chip" onclick="navTo('/records')">記録生成</button>
        <button class="nav-chip" onclick="navTo('/settings')">設定</button>
      </div>
    </div>

    <div class="sidebar-scroll" id="sidebar-scroll">
      <!-- JS で生成 -->
    </div>

    <div class="bottom-bar">
      <button class="btn-back" onclick="undoTheme()">↩ 戻る</button>
      <button class="btn-reset" onclick="resetTheme()">初期値</button>
      <div class="dirty-dot" id="dirty-dot"></div>
      <button class="btn-save" id="save-btn" onclick="saveTheme()">Save</button>
    </div>
  </div>

  <!-- Preview -->
  <div class="preview-area">
    <div class="browser-chrome">
      <div class="browser-dots">
        <div class="browser-dot red"></div>
        <div class="browser-dot yellow"></div>
        <div class="browser-dot green"></div>
      </div>
      <div class="browser-addr" id="browser-addr">http://localhost:5173</div>
      <button class="preview-reload" onclick="reloadFrame()">↻ 再読み込み</button>
    </div>
    <div class="iframe-wrap">
      <iframe id="app-frame" src="http://localhost:5173" allow="same-origin"></iframe>
    </div>
  </div>
</div>

<script>
const SECTIONS = [
  { label: 'アクセント',      vars: ['primary','primary-foreground','accent','accent-foreground'] },
  { label: 'テキスト',        vars: ['foreground','muted-foreground','card-foreground','secondary-foreground'] },
  { label: 'ベース背景',      vars: ['background','card','secondary','muted'] },
  { label: '危険色',          vars: ['destructive','destructive-foreground'] },
  { label: 'ボーダー / 入力', vars: ['border','input','ring'] },
];
const LABELS = {
  background:'背景', foreground:'主要テキスト', card:'カード背景', 'card-foreground':'カードテキスト',
  primary:'プライマリ', 'primary-foreground':'プライマリテキスト',
  secondary:'セカンダリ', 'secondary-foreground':'セカンダリテキスト',
  muted:'ミュート背景', 'muted-foreground':'補助テキスト',
  accent:'アクセント', 'accent-foreground':'アクセントテキスト',
  destructive:'危険色', 'destructive-foreground':'危険色テキスト',
  border:'ボーダー', input:'入力枠', ring:'フォーカスリング',
};
// 各変数がアプリのどこで使われるか（ホバー時に表示）
const USAGE = {
  primary:             '「文字起こし開始」ボタン・アクティブタブ下線',
  'primary-foreground':'プライマリボタン内テキスト',
  accent:              'ホバー・選択状態の背景',
  'accent-foreground': 'アクセント上のテキスト',
  foreground:          'タイトル・本文テキスト全般',
  'muted-foreground':  '「または クリックして選択」等の補足テキスト',
  'card-foreground':   'カード・パネル内のテキスト',
  'secondary-foreground': 'セカンダリボタン内テキスト',
  background:          'ページ全体の背景色',
  card:                'ドロップゾーン・パネルの背景',
  secondary:           '「書き出し」等のセカンダリボタン背景',
  muted:               'テキストエリア・非アクティブ要素の背景',
  destructive:         '削除ボタン・エラー表示',
  'destructive-foreground': '削除ボタン内テキスト',
  border:              'カード枠線・セパレーター',
  input:               'セレクトボックス・入力フィールドの枠',
  ring:                'フォーカス時のアウトライン（Tab キーでわかる）',
};

let theme = { light:{}, dark:{} };
let defaults = { light:{}, dark:{} };
let history = [];   // undo stack
let mode = 'light';

// HSL "H S% L%" ↔ hex 変換
function hslStrToHex(s) {
  const [h,sv,lv] = s.trim().split(/\s+/);
  return hslToHex(+h, parseFloat(sv)/100, parseFloat(lv)/100);
}
function hslToHex(h,s,l) {
  const a = s*Math.min(l,1-l);
  const f = n => {
    const k=(n+h/30)%12;
    return Math.round(255*(l-a*Math.max(Math.min(k-3,9-k,1),-1))).toString(16).padStart(2,'0');
  };
  return `#${f(0)}${f(8)}${f(4)}`;
}
function hexToHslStr(hex) {
  const r=parseInt(hex.slice(1,3),16)/255, g=parseInt(hex.slice(3,5),16)/255, b=parseInt(hex.slice(5,7),16)/255;
  const max=Math.max(r,g,b), min=Math.min(r,g,b);
  let h=0,s=0,l=(max+min)/2;
  if (max!==min) {
    const d=max-min;
    s=l>0.5?d/(2-max-min):d/(max+min);
    switch(max){case r:h=((g-b)/d+(g<b?6:0))/6;break;case g:h=((b-r)/d+2)/6;break;case b:h=((r-g)/d+4)/6;break;}
  }
  return `${Math.round(h*360)} ${Math.round(s*100)}% ${Math.round(l*100)}%`;
}

// ── インスペクター ──
let inspectorOn = false;

function toggleInspector() {
  inspectorOn = !inspectorOn;
  const btn = document.getElementById('inspector-btn');
  btn.classList.toggle('active', inspectorOn);
  btn.textContent = inspectorOn ? '✕ 選択中...' : '◎ 要素を選択';
  const frame = document.getElementById('app-frame');
  try { frame.contentWindow.postMessage({type:'inspector-mode', enabled: inspectorOn}, '*'); } catch(e){}
}

// iframe からのインスペクタークリックを受信してサイドバーをハイライト
window.addEventListener('message', (e) => {
  if (e.data?.type !== 'inspector-click') return;
  const vars = e.data.vars || [];
  // インスペクターOFF に戻す
  inspectorOn = false;
  const btn = document.getElementById('inspector-btn');
  btn.classList.remove('active');
  btn.textContent = '◎ 要素を選択';
  const frame = document.getElementById('app-frame');
  try { frame.contentWindow.postMessage({type:'inspector-mode', enabled: false}, '*'); } catch(e){}
  // 該当サイドバー行をハイライト
  document.querySelectorAll('.color-row.inspected').forEach(r => r.classList.remove('inspected'));
  let firstRow = null;
  for (const varName of vars) {
    const name = varName.replace(/^--/, '');
    const input = document.querySelector(`input[data-name="${name}"]`);
    if (!input) continue;
    const row = input.closest('.color-row');
    if (!row) continue;
    row.classList.add('inspected');
    // セクションを展開
    const body = row.closest('.sec-body');
    if (body && !body.classList.contains('open')) {
      body.classList.add('open');
      body.previousElementSibling?.classList.add('open');
    }
    if (!firstRow) firstRow = row;
  }
  if (firstRow) firstRow.scrollIntoView({behavior:'smooth', block:'center'});
  // 3秒後にハイライト解除
  setTimeout(() => {
    document.querySelectorAll('.color-row.inspected').forEach(r => r.classList.remove('inspected'));
  }, 3000);
});

// ホバー時に変数を一瞬マゼンタにしてどこが変わるか見せる
// shadcn/ui 形式: HSL 成分のみ (hsl() ラップなし)
function flashVar(name, enter) {
  const frame = document.getElementById('app-frame');
  if (enter) {
    const flashVars = { [`--${name}`]: '300 100% 50%' };
    try { frame.contentWindow.postMessage({type:'theme-update', vars:flashVars}, '*'); } catch(e){}
  } else {
    pushToFrame();
  }
}

// iframe に CSS 変数を postMessage で送る
// shadcn/ui は --primary: "0 0% 9%" (HSL成分のみ) を hsl(var(--primary)) で使うので
// hsl() を付けずにそのまま渡す
function pushToFrame() {
  const frame = document.getElementById('app-frame');
  const vars = theme[mode];
  const cssVars = {};
  for (const [name, val] of Object.entries(vars)) {
    cssVars[`--${name}`] = val; // "0 0% 9%" or "0.5rem" — ラップしない
  }
  try {
    frame.contentWindow.postMessage({ type: 'theme-update', vars: cssVars }, '*');
  } catch(e) {}
}

function renderSidebar() {
  const vars = theme[mode];
  let html = '';
  for (const sec of SECTIONS) {
    const isOpen = true;
    html += `<div class="sec">
      <div class="sec-hd open" onclick="toggleSec(this)">
        ${sec.label} <span class="arrow">▲</span>
      </div>
      <div class="sec-body open">`;
    for (const name of sec.vars) {
      const val = vars[name] || '0 0% 50%';
      let hex = '#808080';
      try { hex = hslStrToHex(val); } catch(e) {}
      html += `<div class="color-row" onmouseenter="flashVar('${name}',true)" onmouseleave="flashVar('${name}',false)">
        <div class="swatch" style="background:${hex}" id="sw-${name}">
          <input type="color" value="${hex}" data-name="${name}" oninput="onColor(this)">
        </div>
        <div class="color-lbl-wrap">
          <span class="color-lbl">${LABELS[name]||name}</span>
          ${USAGE[name] ? `<span class="color-usage">→ ${USAGE[name]}</span>` : ''}
        </div>
        <span class="color-hex" id="hx-${name}">${hex}</span>
      </div>`;
    }
    html += `</div></div>`;
  }
  // radius
  const r = parseFloat(vars.radius || '0.5');
  html += `<div class="sec">
    <div class="sec-hd open" onclick="toggleSec(this)">シェイプ <span class="arrow">▲</span></div>
    <div class="sec-body open">
      <div class="radius-wrap">
        <div class="radius-lbl">角丸 (radius) <span id="rad-val">${r}rem</span></div>
        <input type="range" min="0" max="1.5" step="0.05" value="${r}" oninput="onRadius(this)">
      </div>
    </div>
  </div>`;
  document.getElementById('sidebar-scroll').innerHTML = html;
}

function toggleSec(hd) {
  hd.classList.toggle('open');
  hd.nextElementSibling.classList.toggle('open');
}

function onColor(input) {
  pushHistory();
  const name = input.dataset.name;
  const hex = input.value;
  theme[mode][name] = hexToHslStr(hex);
  document.getElementById(`sw-${name}`).style.background = hex;
  document.getElementById(`hx-${name}`).textContent = hex;
  pushToFrame();
  markDirty();
}

function onRadius(input) {
  pushHistory();
  const r = parseFloat(input.value);
  document.getElementById('rad-val').textContent = r + 'rem';
  theme.light.radius = r + 'rem';
  theme.dark.radius = r + 'rem';
  pushToFrame();
  markDirty();
}

function setMode(m) {
  mode = m;
  document.querySelectorAll('.mode-btn').forEach((b,i) =>
    b.classList.toggle('active',(i===0&&m==='light')||(i===1&&m==='dark')));
  renderSidebar();
  pushToFrame();
}

function markDirty() {
  document.getElementById('dirty-dot').classList.add('show');
  document.getElementById('save-btn').textContent = 'Save *';
}

function pushHistory() {
  history.push(JSON.stringify(theme));
  if (history.length > 50) history.shift();
}

function undoTheme() {
  if (!history.length) return;
  theme = JSON.parse(history.pop());
  renderSidebar();
  pushToFrame();
  markDirty();
}

function resetTheme() {
  pushHistory();
  theme = JSON.parse(JSON.stringify(defaults));
  renderSidebar();
  pushToFrame();
  markDirty();
}

async function saveTheme() {
  const light = {...theme.light};
  const dark  = {...theme.dark};
  const res = await fetch('/api/theme', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({light, dark}),
  });
  if (res.ok) {
    const btn = document.getElementById('save-btn');
    btn.textContent = '✓ 保存済み';
    btn.classList.add('saved');
    document.getElementById('dirty-dot').classList.remove('show');
    setTimeout(() => { btn.textContent = 'Save'; btn.classList.remove('saved'); }, 2000);
  }
}

function loadApp() {
  const url = document.getElementById('app-url').value.trim();
  const frame = document.getElementById('app-frame');
  frame.src = url;
  document.getElementById('browser-addr').textContent = url;
}

function reloadFrame() {
  const frame = document.getElementById('app-frame');
  frame.src = frame.src;
  // 再読み込み後に再度テーマを送信
  frame.onload = () => { pushToFrame(); frame.onload = null; };
}

function navTo(path) {
  const base = document.getElementById('app-url').value.trim().replace(/\/$/, '');
  const frame = document.getElementById('app-frame');
  frame.src = base + path;
  document.getElementById('browser-addr').textContent = base + path;
  frame.onload = () => { pushToFrame(); frame.onload = null; };
}

// iframe 読み込み完了後にテーマを再送
document.getElementById('app-frame').addEventListener('load', () => {
  setTimeout(pushToFrame, 200);
});

async function init() {
  const res = await fetch('/api/theme');
  const data = await res.json();
  theme = data;
  defaults = JSON.parse(JSON.stringify(data));
  renderSidebar();
}

init();
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return HTML


if __name__ == "__main__":
    webbrowser.open(f"http://localhost:{PORT}")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
