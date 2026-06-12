import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// Tailwind クラス → CSS 変数名のマッピング（shadcn/ui 標準）
const CLS_TO_VAR: Record<string, string> = {
  'bg-background': '--background',      'bg-card': '--card',
  'bg-primary': '--primary',            'bg-secondary': '--secondary',
  'bg-muted': '--muted',                'bg-accent': '--accent',
  'bg-destructive': '--destructive',    'bg-popover': '--popover',
  'text-foreground': '--foreground',    'text-card-foreground': '--card-foreground',
  'text-primary': '--primary',          'text-primary-foreground': '--primary-foreground',
  'text-secondary-foreground': '--secondary-foreground',
  'text-muted-foreground': '--muted-foreground',
  'text-accent-foreground': '--accent-foreground',
  'text-destructive': '--destructive',  'text-destructive-foreground': '--destructive-foreground',
  'text-popover-foreground': '--popover-foreground',
  'border-border': '--border',          'border-input': '--input',
  'ring-ring': '--ring',                'border-destructive': '--destructive',
  // data-state 付きクラスも対象
  'data-[state=active]:bg-background': '--background',
}

// shadcn/ui CSS変数の全候補（逆引き用）
const ALL_VARS = [
  '--background','--foreground','--card','--card-foreground',
  '--primary','--primary-foreground','--secondary','--secondary-foreground',
  '--muted','--muted-foreground','--accent','--accent-foreground',
  '--destructive','--destructive-foreground','--border','--input','--ring',
]

// rgb文字列を正規化して比較しやすい形に
function normalizeRgb(rgb: string): string {
  const m = rgb.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/)
  if (!m) return rgb
  return `${m[1]},${m[2]},${m[3]}`
}

// computed color → CSS 変数の逆引き
function findVarsByColor(el: Element): string[] {
  const rootStyle = getComputedStyle(document.documentElement)
  const elStyle = getComputedStyle(el)
  const found = new Set<string>()

  // 要素の色プロパティを収集
  const elColors = [
    elStyle.backgroundColor, elStyle.color, elStyle.borderTopColor,
  ].map(normalizeRgb).filter(c => c !== '0,0,0' && c !== '255,255,255' && !c.includes('rgba(0,0,0,0)'))

  for (const varName of ALL_VARS) {
    const varHsl = rootStyle.getPropertyValue(varName).trim()
    if (!varHsl) continue
    // CSS変数値をhsl()で解決してrgbを取得
    const tmp = document.createElement('div')
    tmp.style.color = `hsl(${varHsl})`
    document.body.appendChild(tmp)
    const resolved = normalizeRgb(getComputedStyle(tmp).color)
    document.body.removeChild(tmp)
    if (elColors.includes(resolved)) found.add(varName)
  }
  return [...found]
}

function collectVars(el: Element): string[] {
  const found = new Set<string>()

  // 1. Tailwind クラス名マッチ（要素 + 先祖）
  let cur: Element | null = el
  while (cur && cur !== document.documentElement) {
    cur.classList.forEach(cls => {
      const v = CLS_TO_VAR[cls]
      if (v) found.add(v)
    })
    cur = cur.parentElement
  }

  // 2. computed color 逆引き（クラスで検出できなかった場合の補完）
  if (found.size === 0) {
    findVarsByColor(el).forEach(v => found.add(v))
    // 親要素も1段確認
    if (el.parentElement) {
      findVarsByColor(el.parentElement).forEach(v => found.add(v))
    }
  }

  return [...found]
}

// インスペクター用オーバーレイ（遅延生成）
let inspectorActive = false
let overlay: HTMLDivElement | null = null

function getOverlay(): HTMLDivElement {
  if (!overlay) {
    overlay = document.createElement('div')
    overlay.style.cssText = [
      'position:fixed', 'pointer-events:none', 'z-index:99999',
      'border:2px solid #3b82f6', 'border-radius:4px',
      'background:rgba(59,130,246,0.08)', 'display:none',
      'transition:top .06s,left .06s,width .06s,height .06s',
    ].join(';')
    document.body.appendChild(overlay)
  }
  return overlay
}

document.addEventListener('mouseover', (e: MouseEvent) => {
  if (!inspectorActive) return
  const el = e.target as Element
  const r = el.getBoundingClientRect()
  const ov = getOverlay()
  Object.assign(ov.style, {
    display: 'block',
    top: `${r.top}px`, left: `${r.left}px`,
    width: `${r.width}px`, height: `${r.height}px`,
  })
})

document.addEventListener('click', (e: MouseEvent) => {
  if (!inspectorActive) return
  e.preventDefault()
  e.stopPropagation()
  const vars = collectVars(e.target as Element)
  window.parent.postMessage({ type: 'inspector-click', vars }, '*')
}, true)

window.addEventListener('message', (e: MessageEvent) => {
  // Theme Studio → app: CSS 変数をリアルタイム更新
  if (e.data?.type === 'theme-update') {
    const root = document.documentElement
    for (const [k, v] of Object.entries(e.data.vars as Record<string, string>)) {
      root.style.setProperty(k, v)
    }
  }
  // Theme Studio → app: インスペクターモード切替
  if (e.data?.type === 'inspector-mode') {
    inspectorActive = e.data.enabled as boolean
    document.body.style.cursor = inspectorActive ? 'crosshair' : ''
    const ov = getOverlay()
    ov.style.display = 'none'
  }
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
