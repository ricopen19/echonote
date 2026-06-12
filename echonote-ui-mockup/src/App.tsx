import { useState, useRef } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";

// ── 疑似セグメントデータ（30分音声想定） ──
const MOCK_SEGMENTS = [
  { start: 0.5, end: 4.2, text: "本日はお忙しい中お集まりいただきありがとうございます。" },
  { start: 4.8, end: 9.1, text: "では早速、第一四半期の売上報告から始めさせていただきます。" },
  { start: 9.9, end: 15.3, text: "1月の売上は前年比112%、2月は108%、3月は121%となっています。" },
  { start: 601.2, end: 606.8, text: "次に開発チームからの進捗報告です。" },
  { start: 607.3, end: 614.0, text: "先月リリースした新機能については、ユーザーからの反応が良好です。" },
  { start: 614.5, end: 620.1, text: "バグ修正は現在5件対応中で、今週中に完了予定です。" },
  { start: 621.0, end: 628.4, text: "来月のスプリントではパフォーマンス改善を中心に取り組む予定です。" },
  { start: 1201.5, end: 1207.2, text: "最後にマーケティング部門からのご報告です。" },
  { start: 1208.0, end: 1215.6, text: "SNSのフォロワー数は先月比で15%増加し、現在3万人を超えています。" },
  { start: 1216.2, end: 1222.8, text: "来月のキャンペーンについてはまた詳細を共有します。" },
  { start: 1223.5, end: 1229.0, text: "以上で本日の定例会議を終わります。ありがとうございました。" },
];

// チャンク設定
const CHUNKS = [
  { idx: 0, total: 3, startMin: 0, endMin: 10, segCount: 3 },
  { idx: 1, total: 3, startMin: 10, endMin: 20, segCount: 4 },
  { idx: 2, total: 3, startMin: 20, endMin: 30, segCount: 4 },
];

type Phase =
  | "idle"
  | "loading"
  | "chunk0_start"
  | "chunk0_segs"
  | "chunk1_start"
  | "chunk1_segs"
  | "chunk2_start"
  | "chunk2_segs"
  | "done";

function formatTime(sec: number) {
  const m = Math.floor(sec / 60).toString().padStart(2, "0");
  const s = Math.floor(sec % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

function StatusBadge({ phase }: { phase: Phase }) {
  if (phase === "idle" || phase === "done") return null;
  if (phase === "loading") {
    return (
      <div className="flex items-center gap-2 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
        <Spinner /> モデルを読み込み中...
      </div>
    );
  }
  const chunkIdx = phase.startsWith("chunk0") ? 0 : phase.startsWith("chunk1") ? 1 : 2;
  const c = CHUNKS[chunkIdx];
  const progress = ((chunkIdx + (phase.endsWith("segs") ? 1 : 0)) / 3) * 100;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 text-sm text-blue-700 bg-blue-50 border border-blue-200 rounded px-3 py-2">
        <Spinner />
        <span>
          チャンク {c.idx + 1} / {c.total} 処理中
          <span className="text-blue-500 ml-1">（{c.startMin}〜{c.endMin} 分）</span>
        </span>
      </div>
      <Progress value={progress} className="h-1.5" />
    </div>
  );
}

function DoneStatus({ count }: { count: number }) {
  return (
    <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 border border-green-200 rounded px-3 py-2">
      <span>✅</span>
      <span>文字起こし完了（{count} セグメント）</span>
    </div>
  );
}

function Spinner() {
  return (
    <svg className="animate-spin h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
    </svg>
  );
}

function TranscriptDisplay({ segments, phase }: { segments: typeof MOCK_SEGMENTS; phase: Phase }) {
  if (segments.length === 0) {
    return (
      <div className="text-sm text-zinc-400 italic">
        {phase === "idle" ? "文字起こし結果がここに表示されます" : ""}
      </div>
    );
  }
  return (
    <div className="space-y-1.5">
      {segments.map((seg, i) => (
        <div key={i} className="flex gap-2 text-sm leading-relaxed">
          <span className="text-zinc-400 font-mono shrink-0 tabular-nums">{formatTime(seg.start)}</span>
          <span className="text-zinc-800">{seg.text}</span>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [visibleSegs, setVisibleSegs] = useState<typeof MOCK_SEGMENTS>([]);
  const [fileLabel, setFileLabel] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function clearTimers() {
    timerRef.current.forEach(clearTimeout);
    timerRef.current = [];
  }

  function schedule(fn: () => void, ms: number) {
    timerRef.current.push(setTimeout(fn, ms));
  }

  function handleStart() {
    clearTimers();
    setVisibleSegs([]);
    setPhase("loading");

    // Loading → chunk0 start
    schedule(() => {
      setPhase("chunk0_start");
    }, 1200);

    // chunk0 segs 順に追加
    const chunk0Segs = MOCK_SEGMENTS.slice(0, 3);
    chunk0Segs.forEach((seg, i) => {
      schedule(() => {
        setPhase("chunk0_segs");
        setVisibleSegs((prev) => [...prev, seg]);
      }, 2000 + i * 700);
    });

    // chunk1 start
    schedule(() => setPhase("chunk1_start"), 4200);
    const chunk1Segs = MOCK_SEGMENTS.slice(3, 7);
    chunk1Segs.forEach((seg, i) => {
      schedule(() => {
        setPhase("chunk1_segs");
        setVisibleSegs((prev) => [...prev, seg]);
      }, 5000 + i * 700);
    });

    // chunk2 start
    schedule(() => setPhase("chunk2_start"), 8000);
    const chunk2Segs = MOCK_SEGMENTS.slice(7);
    chunk2Segs.forEach((seg, i) => {
      schedule(() => {
        setPhase("chunk2_segs");
        setVisibleSegs((prev) => [...prev, seg]);
      }, 8800 + i * 700);
    });

    // done
    schedule(() => setPhase("done"), 11800);
  }

  function handleReset() {
    clearTimers();
    setPhase("idle");
    setVisibleSegs([]);
    setFileLabel(null);
  }

  const isRunning = phase !== "idle" && phase !== "done";

  return (
    <div className="min-h-screen bg-background text-foreground flex items-start justify-center py-8 px-4">
      <div className="w-full max-w-3xl">
        {/* Header */}
        <div className="mb-4">
          <h1 className="text-xl font-semibold text-zinc-900 tracking-tight">Echonote 🎧</h1>
          <p className="text-sm text-zinc-500 mt-0.5">音声ファイルから構造化テキスト記録を生成します。</p>
        </div>

        <Tabs defaultValue="transcribe" className="w-full">
          <TabsList className="bg-white border border-zinc-200 rounded-none h-9 p-0 gap-0">
            <TabsTrigger value="transcribe" className="rounded-none text-xs px-4 h-full data-[state=active]:bg-zinc-900 data-[state=active]:text-white">
              📝 文字起こし
            </TabsTrigger>
            <TabsTrigger value="generate" className="rounded-none text-xs px-4 h-full data-[state=active]:bg-zinc-900 data-[state=active]:text-white">
              📄 記録生成
            </TabsTrigger>
            <TabsTrigger value="settings" className="rounded-none text-xs px-4 h-full data-[state=active]:bg-zinc-900 data-[state=active]:text-white">
              ⚙️ 設定
            </TabsTrigger>
          </TabsList>

          {/* ── 文字起こしタブ ── */}
          <TabsContent value="transcribe" className="mt-0 border border-t-0 border-zinc-200 bg-white p-5 space-y-4">
            {/* 入力行 */}
            <div className="flex gap-4">
              {/* ファイルドロップ */}
              <div
                className="flex-1 border-2 border-dashed border-zinc-300 rounded bg-zinc-50 flex flex-col items-center justify-center py-6 cursor-pointer hover:border-zinc-400 transition-colors"
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="audio/*"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) setFileLabel(f.name);
                  }}
                />
                {fileLabel ? (
                  <div className="text-center">
                    <div className="text-2xl mb-1">🎵</div>
                    <p className="text-sm text-zinc-700 font-medium">{fileLabel}</p>
                    <p className="text-xs text-zinc-400 mt-0.5">クリックで変更</p>
                  </div>
                ) : (
                  <div className="text-center">
                    <div className="text-2xl mb-1">📂</div>
                    <p className="text-sm text-zinc-500">音声ファイルをドロップ</p>
                    <p className="text-xs text-zinc-400 mt-0.5">または クリックして選択</p>
                  </div>
                )}
              </div>

              {/* モデル・言語選択 */}
              <div className="w-44 space-y-3">
                <div className="space-y-1">
                  <Label className="text-xs text-zinc-500">Whisper モデル</Label>
                  <Select defaultValue="medium">
                    <SelectTrigger className="h-8 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {["tiny","base","small","medium","large-v2","large-v3","large-v3-turbo"].map(m => (
                        <SelectItem key={m} value={m} className="text-xs">{m}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs text-zinc-500">言語</Label>
                  <Select defaultValue="ja">
                    <SelectTrigger className="h-8 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ja" className="text-xs">ja</SelectItem>
                      <SelectItem value="en" className="text-xs">en</SelectItem>
                      <SelectItem value="auto" className="text-xs">auto</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-center gap-2">
                  <Checkbox id="diarize" className="h-3.5 w-3.5" />
                  <Label htmlFor="diarize" className="text-xs text-zinc-500 leading-tight">話者分離を実行（HF トークン必須）</Label>
                </div>
              </div>
            </div>

            {/* 実行ボタン */}
            <div className="flex gap-2 items-center">
              <Button
                onClick={handleStart}
                disabled={isRunning}
                size="sm"
                className="bg-zinc-900 hover:bg-zinc-700 text-white text-xs"
              >
                {isRunning ? "処理中..." : "▶ 文字起こし開始"}
              </Button>
              {phase !== "idle" && (
                <Button variant="ghost" size="sm" onClick={handleReset} className="text-xs text-zinc-400">
                  リセット
                </Button>
              )}
              {phase === "done" && (
                <Badge variant="outline" className="text-xs text-green-700 border-green-300 ml-1">
                  {visibleSegs.length} セグメント
                </Badge>
              )}
            </div>

            {/* ── ここが P3-1 の新規追加部分 ── */}
            {phase !== "idle" && phase !== "done" && <StatusBadge phase={phase} />}
            {phase === "done" && <DoneStatus count={visibleSegs.length} />}

            {/* 結果ボックス */}
            <div className="border border-zinc-200 rounded bg-zinc-50 min-h-48 max-h-80 overflow-y-auto p-3">
              <TranscriptDisplay segments={visibleSegs} phase={phase} />
            </div>

            {/* ヒント */}
            {phase === "idle" && (
              <p className="text-xs text-zinc-400">
                ※ 30分音声は自動的に 10分チャンクに分割して処理します（OOM 対策）
              </p>
            )}
          </TabsContent>

          {/* ── 記録生成タブ ── */}
          <TabsContent value="generate" className="mt-0 border border-t-0 border-zinc-200 bg-white p-5 space-y-3">
            <div className="space-y-1">
              <Label className="text-xs text-zinc-500">テンプレート</Label>
              <Select defaultValue="meeting">
                <SelectTrigger className="h-8 text-xs w-48">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="meeting" className="text-xs">会議議事録</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-zinc-500">プロンプト（編集可能）</Label>
              <Textarea className="text-xs h-28 resize-none" defaultValue="以下の文字起こしを元に会議議事録を作成してください。&#10;&#10;{transcript}" />
            </div>
            <Button size="sm" className="bg-zinc-900 hover:bg-zinc-700 text-white text-xs" disabled>
              ▶ 記録を生成
            </Button>
            <p className="text-xs text-zinc-400">先に文字起こしタブで転写を実行してください。</p>
          </TabsContent>

          {/* ── 設定タブ ── */}
          <TabsContent value="settings" className="mt-0 border border-t-0 border-zinc-200 bg-white p-5 space-y-4">
            <div className="space-y-1">
              <Label className="text-xs text-zinc-500">LLM エンドポイント</Label>
              <div className="flex gap-2">
                {["Ollama (localhost:11434)", "mlx-lm (localhost:8080)"].map(o => (
                  <button
                    key={o}
                    className="text-xs border border-zinc-300 rounded px-3 py-1.5 bg-white hover:bg-zinc-50 first:bg-zinc-900 first:text-white first:border-zinc-900"
                  >
                    {o}
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-zinc-500">エンドポイント URL</Label>
              <input className="w-full border border-zinc-300 rounded px-3 py-1.5 text-xs" defaultValue="http://localhost:11434/v1" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-zinc-500">LLM モデル名</Label>
              <input className="w-full border border-zinc-300 rounded px-3 py-1.5 text-xs" defaultValue="qwen3:4b-q4_K_M" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-zinc-500">HuggingFace トークン（話者分離用）</Label>
              <input type="password" className="w-full border border-zinc-300 rounded px-3 py-1.5 text-xs" placeholder="hf_..." />
            </div>
            <Button size="sm" variant="outline" className="text-xs">設定を適用</Button>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
