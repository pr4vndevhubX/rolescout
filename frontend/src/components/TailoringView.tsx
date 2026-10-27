export default function TailoringView({ data }: { data: any }) {
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
            {data.bullet_rewrites.map((b: any, i: number) => (
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
          {data.surfaceable_skills.map((s: any, i: number) => (
            <p key={i} className="text-xs"><span className="font-semibold text-white">{s.skill}</span>
              <span className="text-slate-500"> — {s.evidence}</span></p>
          ))}
        </section>
      )}
      {data.ats_keywords_to_add?.length > 0 && (
        <section>
          <h4 className="mb-1 text-xs font-bold uppercase tracking-wide text-indigo-300">ATS keywords to weave in</h4>
          <div className="flex flex-wrap gap-1.5">
            {data.ats_keywords_to_add.map((k: string) => (
              <span key={k} className="chip bg-sky-500/12 text-sky-300 ring-1 ring-sky-400/20">{k}</span>
            ))}
          </div>
        </section>
      )}
      {data.honest_gaps?.length > 0 && (
        <section>
          <h4 className="mb-1 text-xs font-bold uppercase tracking-wide text-rose-300">Honest gaps (don't fake these)</h4>
          {data.honest_gaps.map((g: any, i: number) => (
            <p key={i} className="text-xs"><span className="font-semibold text-white">{g.skill}</span>
              <span className="text-slate-500"> — {g.suggestion}</span></p>
          ))}
        </section>
      )}
    </div>
  );
}
