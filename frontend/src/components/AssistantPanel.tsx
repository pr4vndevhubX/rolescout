import { useEffect, useRef, useState } from "react";
import { Bot, Send, Loader2, PlayCircle, ChevronDown, Wrench } from "lucide-react";
import { api, type ToastFn } from "../api";

function ActionRow({ action }: { action: any }) {
  return (
    <div className="flex items-start gap-2 text-[11px] leading-relaxed">
      <Wrench size={11} className="mt-0.5 shrink-0 text-slate-600" />
      <div className="min-w-0">
        <span className="font-semibold text-slate-400">{action.tool}</span>{" "}
        <span className="break-words text-slate-500">{action.result?.slice(0, 160)}</span>
      </div>
    </div>
  );
}

export default function AssistantPanel({ toast }: { toast: ToastFn }) {
  const [messages, setMessages] = useState<{ role: string; text: string; actions?: any[] }[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState(false);
  const [runs, setRuns] = useState<any[]>([]);
  const [showActivity, setShowActivity] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const refreshRuns = () => api.assistantRuns(8).then((r) => setRuns(r.runs)).catch(() => {});
  useEffect(() => { refreshRuns(); }, []);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  async function send() {
    const message = input.trim();
    if (!message || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: message }]);
    setBusy(true);
    try {
      const r = await api.assistantChat(message);
      setMessages((m) => [...m, { role: "assistant", text: r.reply, actions: r.actions }]);
      refreshRuns();
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", text: `Something went wrong: ${e.message}` }]);
    } finally {
      setBusy(false);
    }
  }

  async function runNow() {
    setRunning(true);
    try {
      const r = await api.assistantRun();
      toast(r.summary || "Assistant cycle finished.", "success");
      refreshRuns();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="glass animate-fade-up flex flex-col p-5">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bot size={16} className="text-fuchsia-300" />
          <h2 className="font-bold text-white">Your Assistant</h2>
        </div>
        <button className="btn-ghost !px-3 !py-1.5 text-xs" onClick={runNow} disabled={running}>
          {running ? <Loader2 size={14} className="animate-spin" /> : <PlayCircle size={14} />}
          {running ? "Working..." : "Run daily cycle now"}
        </button>
      </div>

      {/* Chat thread */}
      <div ref={scrollRef} className="max-h-72 space-y-3 overflow-y-auto pr-1">
        {messages.length === 0 && (
          <p className="py-4 text-center text-xs text-slate-600">
            Ask me things like “find me GenAI jobs”, “tailor my resume for the best match”,
            or “what did you find today?”
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`${m.role === "user" ? "ml-8" : "mr-4"}`}>
            <div className={`rounded-xl px-3 py-2 text-xs leading-relaxed ${
              m.role === "user"
                ? "bg-indigo-500/20 text-indigo-100"
                : "border border-white/[0.06] bg-slate-950/40 text-slate-300"}`}>
              <p className="whitespace-pre-wrap">{m.text}</p>
              {m.actions && m.actions.length > 0 && (
                <div className="mt-2 space-y-1 border-t border-white/[0.06] pt-2">
                  {m.actions.map((a, j) => <ActionRow key={j} action={a} />)}
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && (
          <p className="flex items-center gap-2 text-xs text-fuchsia-300">
            <Loader2 size={13} className="animate-spin" /> thinking &amp; using tools...
          </p>
        )}
      </div>

      {/* Input */}
      <div className="mt-3 flex gap-2">
        <input className="input-dark flex-1" placeholder="Tell your assistant what to do..."
          value={input} onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()} disabled={busy} />
        <button className="btn-primary !px-3" onClick={send} disabled={busy || !input.trim()}>
          <Send size={15} />
        </button>
      </div>

      {/* Activity feed */}
      <button onClick={() => setShowActivity(!showActivity)}
        className="mt-3 flex items-center justify-center gap-1 text-[11px] text-slate-500 transition hover:text-slate-300">
        Activity log ({runs.length} recent runs)
        <ChevronDown size={13} className={`transition-transform ${showActivity ? "rotate-180" : ""}`} />
      </button>
      {showActivity && (
        <div className="mt-2 max-h-48 space-y-2 overflow-y-auto">
          {runs.map((r) => (
            <div key={r.run_id} className="rounded-xl border border-white/[0.06] bg-slate-950/40 p-2.5">
              <div className="flex items-center justify-between text-[11px]">
                <span className={`font-semibold ${
                  r.status === "completed" ? "text-emerald-300" :
                  r.status === "failed" ? "text-rose-300" : "text-amber-300"}`}>
                  {r.trigger} · {r.status}
                </span>
                <span className="text-slate-600">{new Date(r.started_at).toLocaleString()}</span>
              </div>
              {r.summary && <p className="mt-1 text-[11px] text-slate-400">{r.summary}</p>}
              {r.actions?.length > 0 && (
                <div className="mt-1.5 space-y-1">{r.actions.map((a: any, j: number) => <ActionRow key={j} action={a} />)}</div>
              )}
            </div>
          ))}
          {runs.length === 0 && <p className="text-center text-[11px] text-slate-600">No runs yet.</p>}
        </div>
      )}
    </div>
  );
}
