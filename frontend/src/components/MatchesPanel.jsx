import { useEffect, useState } from "react";
import { Target, Loader2, Sparkles, Copy } from "lucide-react";
import { api } from "../api";
import MatchCard from "./MatchCard";
import Modal from "./Modal";

function TailoringView({ data }) {
  return (
    <div className="space-y-4 text-sm text-slate-300">
      {data.tailored_summary && (
        <section>
          <h4 className="mb-1 text-xs font-bold uppercase tracking-wide text-indigo-300">Tailored summary</h4>
          <p className="rounded-xl border border-white/[0.06] bg-slate-950/40 p-3 text-xs leading-relaxed">{data.tailored_summary}</p>
        </section>
      )}
      {data.bullet_rewrites?.length > 0 && (
        <section>
          <h4 className="mb-1 text-xs font-bold uppercase tracking-wide text-indigo-300">Bullet rewrites</h4>
          <div className="space-y-2">
            {data.bullet_rewrites.map((b, i) => (
              <div key={i} className="rounded-xl border border-white/[0.06] bg-slate-950/40 p-3 text-xs">
                <p className="text-slate-500 line-through">{b.original}</p>
                <p className="mt-1 text-emerald-300">{b.rewritten}</p>
              </div>
            ))}
          </div>
        </section>
      )}
      {data.surfaceable_skills?.length > 0 && (
        <section>
          <h4 className="mb-1 text-xs font-bold uppercase tracking-wide text-indigo-300">Skills you can truthfully surface</h4>
          {data.surfaceable_skills.map((s, i) => (
            <p key={i} className="text-xs"><span className="font-semibold text-white">{s.skill}</span>
              <span className="text-slate-500"> — {s.evidence}</span></p>
          ))}
        </section>
      )}
      {data.ats_keywords_to_add?.length > 0 && (
        <section>
          <h4 className="mb-1 text-xs font-bold uppercase tracking-wide text-indigo-300">ATS keywords to weave in</h4>
          <div className="flex flex-wrap gap-1.5">
            {data.ats_keywords_to_add.map((k) => (
              <span key={k} className="chip bg-sky-500/12 text-sky-300 ring-1 ring-sky-400/20">{k}</span>
            ))}
          </div>
        </section>
      )}
      {data.honest_gaps?.length > 0 && (
        <section>
          <h4 className="mb-1 text-xs font-bold uppercase tracking-wide text-rose-300">Honest gaps (don't fake these)</h4>
          {data.honest_gaps.map((g, i) => (
            <p key={i} className="text-xs"><span className="font-semibold text-white">{g.skill}</span>
              <span className="text-slate-500"> — {g.suggestion}</span></p>
          ))}
        </section>
      )}
    </div>
  );
}

const PHASES = [
  "Finding semantically similar jobs...",
  "Applying experience & location filters...",
  "AI analyzing skill fit per job...",
  "Computing ATS keyword scores...",
];

export default function MatchesPanel({ resume, toast }) {
  const [matches, setMatches] = useState([]);
  const [generating, setGenerating] = useState(false);
  const [phaseIdx, setPhaseIdx] = useState(0);
  const [filter, setFilter] = useState("");
  const [locationFilter, setLocationFilter] = useState("");
  const [modal, setModal] = useState(null); // {kind: "tailor"|"letter", match, data?, loading}

  // Restore previously generated matches when a resume appears (e.g. after login)
  useEffect(() => {
    if (!resume?.id) { setMatches([]); return; }
    api.listMatches(resume.id).then((r) => setMatches(r.results)).catch(() => {});
  }, [resume?.id]);

  async function generate() {
    if (!resume) return toast("Upload a resume first.", "error");
    setGenerating(true);
    setPhaseIdx(0);
    const ticker = setInterval(() => setPhaseIdx((i) => Math.min(i + 1, PHASES.length - 1)), 4000);
    try {
      const r = await api.generateMatches(resume.id, { location: locationFilter });
      setMatches(r.results);
      toast(`Found ${r.result_count} matching jobs, ranked by fit.`, "success");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      clearInterval(ticker);
      setGenerating(false);
    }
  }

  async function refresh(status) {
    if (!resume) return;
    setFilter(status);
    try {
      const r = await api.listMatches(resume.id, status || undefined);
      setMatches(r.results);
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function setStatus(match, status) {
    try {
      await api.setMatchStatus(match.match_id, status);
      setMatches((ms) => ms.map((m) => (m.match_id === match.match_id ? { ...m, status } : m)));
      if (status === "applied") toast("Marked as applied — tracked in your history.", "success");
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function openTailor(match) {
    setModal({ kind: "tailor", match, loading: true });
    try {
      const data = await api.tailorMatch(match.match_id);
      setModal({ kind: "tailor", match, data, loading: false });
    } catch (e) {
      setModal(null);
      toast(e.message, "error");
    }
  }

  async function openCoverLetter(match) {
    setModal({ kind: "letter", match, loading: true });
    try {
      const data = await api.coverLetter(match.match_id);
      setModal({ kind: "letter", match, data, loading: false });
    } catch (e) {
      setModal(null);
      toast(e.message, "error");
    }
  }

  return (
    <div className="animate-fade-up space-y-4">
      {/* Controls */}
      <div className={`glass flex flex-wrap items-center gap-3 p-4 ${generating ? "glass-active" : ""}`}>
        <input className="input-dark !w-48 flex-1" placeholder="Location filter (optional)"
          value={locationFilter} onChange={(e) => setLocationFilter(e.target.value)} />
        <button className="btn-primary" onClick={generate} disabled={generating || !resume}>
          {generating ? <Loader2 size={16} className="animate-spin" /> : <Target size={16} />}
          {generating ? "Matching..." : "Generate Matches"}
        </button>
        <div className="ml-auto flex gap-1 rounded-xl border border-white/10 bg-slate-900/50 p-1">
          {[["", "All"], ["new", "New"], ["saved", "Saved"], ["applied", "Applied"], ["dismissed", "Dismissed"]].map(([v, l]) => (
            <button key={v} onClick={() => refresh(v)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                filter === v ? "bg-indigo-500/25 text-indigo-200" : "text-slate-500 hover:text-slate-300"}`}>
              {l}
            </button>
          ))}
        </div>
      </div>

      {generating && (
        <div className="glass p-6">
          <div className="shimmer h-2 rounded-full" />
          <p className="mt-3 flex items-center justify-center gap-2 text-xs text-indigo-300">
            <Sparkles size={13} className="animate-pulse" />
            {PHASES[phaseIdx]}
          </p>
        </div>
      )}

      {!generating && matches.length === 0 && (
        <div className="glass flex flex-col items-center p-12 text-center">
          <Target size={36} className="mb-3 text-slate-600" />
          <p className="font-semibold text-slate-400">No matches yet</p>
          <p className="mt-1 max-w-sm text-xs text-slate-600">
            Upload a resume, fetch some jobs, then hit Generate Matches.
          </p>
        </div>
      )}

      {matches.map((m, i) => (
        <div key={m.match_id} style={{ animationDelay: `${Math.min(i * 70, 500)}ms` }} className="animate-fade-up">
          <MatchCard match={m} onStatus={setStatus} onTailor={openTailor} onCoverLetter={openCoverLetter} />
        </div>
      ))}

      {modal && (
        <Modal
          title={modal.kind === "tailor" ? "✂ Tailored for this job" : "📝 Cover letter"}
          subtitle={`${modal.match.title}${modal.match.company ? ` · ${modal.match.company}` : ""}`}
          onClose={() => setModal(null)}
        >
          {modal.loading ? (
            <div className="flex items-center justify-center gap-2 py-10 text-sm text-indigo-300">
              <Loader2 size={16} className="animate-spin" />
              {modal.kind === "tailor"
                ? "Adapting your resume to this JD (truthfully)..."
                : "Writing a letter grounded in your real experience..."}
            </div>
          ) : modal.kind === "tailor" ? (
            <TailoringView data={modal.data} />
          ) : (
            <div>
              <p className="whitespace-pre-wrap rounded-xl border border-white/[0.06] bg-slate-950/40 p-4 text-sm leading-relaxed text-slate-300">
                {modal.data.cover_letter}
              </p>
              <button className="btn-ghost mt-3 !px-3 !py-1.5 text-xs"
                onClick={() => { navigator.clipboard.writeText(modal.data.cover_letter); toast("Copied to clipboard.", "success"); }}>
                <Copy size={13} /> Copy letter
              </button>
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}
