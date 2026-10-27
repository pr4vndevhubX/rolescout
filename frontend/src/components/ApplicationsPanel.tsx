import { useEffect, useState } from "react";
import { Briefcase, MapPin, Building2, ExternalLink, Copy, ThumbsUp, Send, Archive, Package } from "lucide-react";
import { api, type ToastFn } from "../api";
import Modal from "./Modal";
import TailoringView from "./TailoringView";

const TABS: [string, string][] = [
  ["", "All"],
  ["prepared", "Prepared"],
  ["approved", "Approved"],
  ["applied", "Applied"],
  ["discarded", "Discarded"],
];

const STATUS_CHIP: Record<string, string> = {
  prepared: "bg-indigo-500/15 text-indigo-300 ring-1 ring-indigo-400/25",
  approved: "bg-amber-500/15 text-amber-300 ring-1 ring-amber-400/25",
  applied: "bg-sky-500/15 text-sky-300 ring-1 ring-sky-400/25",
  discarded: "bg-rose-500/15 text-rose-300 ring-1 ring-rose-400/25",
};

export default function ApplicationsPanel({ toast }: { toast: ToastFn }) {
  const [applications, setApplications] = useState<any[]>([]);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [modalApp, setModalApp] = useState<any>(null);

  async function refresh(status: string) {
    setLoading(true);
    try {
      const r = await api.listApplications(status || undefined);
      setApplications(r.applications);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh(filter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function setStatus(app: any, status: string) {
    try {
      const updated = await api.setApplicationStatus(app.application_id, status);
      setApplications((apps) =>
        filter && updated.status !== filter
          ? apps.filter((a) => a.application_id !== app.application_id)
          : apps.map((a) => (a.application_id === app.application_id ? updated : a))
      );
      toast(
        status === "applied" ? "Marked as applied — tracked in your history." :
        status === "approved" ? "Approved — go ahead and submit it." :
        "Discarded.",
        "success"
      );
    } catch (e) {
      toast(e.message, "error");
    }
  }

  function changeTab(status: string) {
    setFilter(status);
    refresh(status);
  }

  return (
    <div className="animate-fade-up space-y-4">
      <div className="glass flex flex-wrap items-center gap-3 p-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-white">
          <Package size={16} className="text-indigo-300" /> Applications
        </div>
        <div className="ml-auto flex gap-1 rounded-xl border border-white/10 bg-slate-900/50 p-1">
          {TABS.map(([v, l]) => (
            <button key={v} onClick={() => changeTab(v)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                filter === v ? "bg-indigo-500/25 text-indigo-200" : "text-slate-500 hover:text-slate-300"}`}>
              {l}
            </button>
          ))}
        </div>
      </div>

      {!loading && applications.length === 0 && (
        <div className="glass flex flex-col items-center p-12 text-center">
          <Briefcase size={36} className="mb-3 text-slate-600" />
          <p className="font-semibold text-slate-400">No prepared applications yet</p>
          <p className="mt-1 max-w-sm text-xs text-slate-600">
            The assistant prepares an application package (tailored resume + cover letter) for
            your strong-fit and tailored near-miss matches during a daily run.
          </p>
        </div>
      )}

      {applications.map((a, i) => (
        <div key={a.application_id} style={{ animationDelay: `${Math.min(i * 70, 500)}ms` }}
          className={`glass glass-hover animate-fade-up p-5 ${a.status === "discarded" ? "opacity-50" : ""}`}>
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h3 className="truncate font-bold text-white">{a.title}</h3>
              <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-slate-500">
                {a.company && <span className="flex items-center gap-1"><Building2 size={12} />{a.company}</span>}
                {a.location && <span className="flex items-center gap-1"><MapPin size={12} />{a.location}</span>}
              </p>
            </div>
            <span className={`chip shrink-0 ${STATUS_CHIP[a.status] || ""}`}>{a.status}</span>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-white/[0.06] pt-3">
            <button className="btn-ghost !px-3 !py-1.5 text-xs !text-fuchsia-300 hover:!border-fuchsia-400/40"
              onClick={() => setModalApp(a)}>
              <Package size={14} /> View package
            </button>
            <div className="flex-1" />
            {a.status === "prepared" && (
              <button className="btn-ghost !px-3 !py-1.5 text-xs !text-amber-300 hover:!border-amber-400/40"
                onClick={() => setStatus(a, "approved")}>
                <ThumbsUp size={14} /> Approve
              </button>
            )}
            {(a.status === "prepared" || a.status === "approved") && (
              <button className="btn-ghost !px-3 !py-1.5 text-xs !text-sky-300 hover:!border-sky-400/40"
                onClick={() => setStatus(a, "applied")}>
                <Send size={14} /> Mark applied
              </button>
            )}
            {a.status !== "discarded" && a.status !== "applied" && (
              <button className="btn-ghost !px-3 !py-1.5 text-xs !text-rose-300/80 hover:!border-rose-400/40"
                onClick={() => setStatus(a, "discarded")}>
                <Archive size={14} /> Discard
              </button>
            )}
            {a.apply_url && (
              <a href={a.apply_url} target="_blank" rel="noreferrer" className="btn-primary !px-3 !py-1.5 text-xs">
                Apply <ExternalLink size={13} />
              </a>
            )}
          </div>
        </div>
      ))}

      {modalApp && (
        <Modal
          title="📦 Application package"
          subtitle={`${modalApp.title}${modalApp.company ? ` · ${modalApp.company}` : ""}`}
          onClose={() => setModalApp(null)}
        >
          <div className="space-y-5">
            {modalApp.tailoring && <TailoringView data={modalApp.tailoring} />}
            {modalApp.cover_letter && (
              <section>
                <h4 className="mb-1 text-xs font-bold uppercase tracking-wide text-indigo-300">Cover letter</h4>
                <p className="whitespace-pre-wrap rounded-xl border border-white/[0.06] bg-slate-950/40 p-4 text-sm leading-relaxed text-slate-300">
                  {modalApp.cover_letter}
                </p>
                <button className="btn-ghost mt-3 !px-3 !py-1.5 text-xs"
                  onClick={() => { navigator.clipboard.writeText(modalApp.cover_letter); toast("Copied to clipboard.", "success"); }}>
                  <Copy size={13} /> Copy letter
                </button>
              </section>
            )}
            {!modalApp.tailoring && !modalApp.cover_letter && (
              <p className="text-sm text-slate-500">No tailored content was generated for this package.</p>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
