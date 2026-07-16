import { useEffect, useState } from "react";
import { Settings2, Plus, X, Loader2, Save } from "lucide-react";
import { api } from "../api";

export default function PreferencesPanel({ toast }) {
  const [prefs, setPrefs] = useState(null);
  const [roleInput, setRoleInput] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.getPreferences().then(setPrefs).catch(() => {});
  }, []);

  function addRole() {
    const role = roleInput.trim();
    if (!role || prefs.desired_roles.includes(role)) return;
    setPrefs((p) => ({ ...p, desired_roles: [...p.desired_roles, role] }));
    setRoleInput("");
  }

  async function save() {
    setSaving(true);
    try {
      const saved = await api.savePreferences({
        desired_roles: prefs.desired_roles,
        country: prefs.country || "in",
        location_contains: prefs.location_contains || null,
        min_salary: prefs.min_salary ? Number(prefs.min_salary) : null,
        min_match_score: Number(prefs.min_match_score),
        auto_tailor: prefs.auto_tailor,
        daily_digest_enabled: prefs.daily_digest_enabled,
        notify_email: prefs.notify_email || null,
      });
      setPrefs(saved);
      toast("Preferences saved — the assistant will use them on every run.", "success");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  }

  if (!prefs) return null;

  return (
    <div className="glass animate-fade-up p-5">
      <div className="mb-3 flex items-center gap-2">
        <Settings2 size={16} className="text-indigo-300" />
        <h2 className="font-bold text-white">Assistant Preferences</h2>
      </div>

      <label className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
        Roles I want (e.g. AI/ML Engineer)
      </label>
      <div className="mt-1.5 flex gap-2">
        <input className="input-dark flex-1" placeholder="Machine Learning Engineer"
          value={roleInput}
          onChange={(e) => setRoleInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addRole()} />
        <button className="btn-ghost !px-3" onClick={addRole}><Plus size={15} /></button>
      </div>
      {prefs.desired_roles.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {prefs.desired_roles.map((r) => (
            <span key={r} className="chip flex items-center gap-1 bg-indigo-500/15 text-indigo-200 ring-1 ring-indigo-400/25">
              {r}
              <button onClick={() => setPrefs((p) => ({ ...p, desired_roles: p.desired_roles.filter((x) => x !== r) }))}
                className="text-indigo-300/60 hover:text-white"><X size={11} /></button>
            </span>
          ))}
        </div>
      )}

      <div className="mt-3 grid grid-cols-2 gap-2">
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-slate-500">Country</label>
          <input className="input-dark mt-1" value={prefs.country || ""}
            onChange={(e) => setPrefs((p) => ({ ...p, country: e.target.value }))} placeholder="in" />
        </div>
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-slate-500">Min salary</label>
          <input className="input-dark mt-1" type="number" value={prefs.min_salary ?? ""}
            onChange={(e) => setPrefs((p) => ({ ...p, min_salary: e.target.value }))} placeholder="optional" />
        </div>
      </div>

      <div className="mt-3">
        <label className="flex justify-between text-[11px] font-medium uppercase tracking-wide text-slate-500">
          Strong-fit threshold <span className="text-slate-300">{Math.round(prefs.min_match_score * 100)}%</span>
        </label>
        <input type="range" min="0.3" max="0.8" step="0.05" value={prefs.min_match_score}
          onChange={(e) => setPrefs((p) => ({ ...p, min_match_score: e.target.value }))}
          className="mt-1 w-full accent-indigo-400" />
      </div>

      <div className="mt-3 space-y-2 text-xs text-slate-400">
        <label className="flex cursor-pointer items-center gap-2">
          <input type="checkbox" checked={prefs.auto_tailor} className="accent-indigo-400"
            onChange={(e) => setPrefs((p) => ({ ...p, auto_tailor: e.target.checked }))} />
          Auto-tailor my resume for near-miss jobs
        </label>
        <label className="flex cursor-pointer items-center gap-2">
          <input type="checkbox" checked={prefs.daily_digest_enabled} className="accent-indigo-400"
            onChange={(e) => setPrefs((p) => ({ ...p, daily_digest_enabled: e.target.checked }))} />
          Email me a daily digest of new matches
        </label>
      </div>

      <button className="btn-primary mt-4 w-full" onClick={save} disabled={saving}>
        {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
        Save preferences
      </button>
    </div>
  );
}
