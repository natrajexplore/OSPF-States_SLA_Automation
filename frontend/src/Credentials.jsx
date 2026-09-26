import { useState } from "react";
import { usePoll } from "./api.js";
import { puttyHref } from "./liveState.js";

// Every router of the shared lab and of the standalone labs: SSH address, login, password and enable secret (hidden until
// Reveal), each checked against the router's baseline file. Values come from GET /api/credentials. Leaving the tab hides them.
const DOTS = "••••••";

function Secret({ value, shown, onReveal }) {
  return (
    <span className="secret">
      <code>{shown ? value : DOTS}</code>
      <button className="secondary small" onClick={onReveal}>{shown ? "Hide" : "Reveal"}</button>
      <button className="secondary small" onClick={() => navigator.clipboard?.writeText(value)} title="Copy to the clipboard">Copy</button>
    </span>
  );
}

export default function Credentials() {
  const { data, error } = usePoll("/api/credentials", 60000);
  const [shown, setShown] = useState({});
  const [all, setAll] = useState(false);
  const [q, setQ] = useState("");
  const labs = data?.labs || [];
  const needle = q.trim().toLowerCase();
  const match = (lab, r) => !needle || [lab.id, lab.title, r.name, r.mgmt_ip, r.role].some((s) => String(s).toLowerCase().includes(needle));
  const flip = (k) => setShown((s) => ({ ...s, [k]: !s[k] }));
  const total = labs.reduce((n, l) => n + l.routers.length, 0);
  const differs = labs.flatMap((l) => l.routers.filter((r) => r.baseline_match === false));

  return (
    <>
      {error && <div className="alert bad">Backend: {error}</div>}
      <section className="card">
        <h3>
          Credentials
          <span className="muted small">{total} routers in {labs.length} labs</span>
          <span className="spacer" />
          <input className="filter" placeholder="Filter: lab, router, address…" value={q} onChange={(e) => setQ(e.target.value)} />
          <button className="secondary" onClick={() => { setAll(!all); setShown({}); }}>{all ? "Hide all" : "Reveal all"}</button>
        </h3>
        <p className="muted small">
          The login the dashboard uses (each lab's <code>inventory.yaml</code>, then <code>.env</code>), compared with the <code>username</code> and
          <code> enable secret</code> lines of the router's baseline. <b>SSH session</b> opens the router in its own PuTTY window after the one-time
          {" "}<code>scripts\putty-setup.ps1</code>; PuTTY asks for the password, then type <code>enable</code> and the enable secret.
          The dots only hide the values on screen: anyone who can open the dashboard can read <code>/api/credentials</code>.
        </p>
        {differs.length > 0 && <div className="alert bad">{differs.length} router(s) have a baseline login that differs from the inventory.</div>}
        <p className="muted small">
          All labs share the management addresses 192.168.99.11-14, so only the running lab answers. Sessions differ by name and window title.
        </p>
      </section>
      {labs.map((lab) => {
        const rows = lab.routers.filter((r) => match(lab, r));
        if (!rows.length) return null;
        return (
          <details className="card" key={lab.id} open={lab.id === "shared" || !!needle}>
            <summary>
              <b>{lab.id}</b> <span className="muted">{lab.title}</span> <span className="muted small">EVE {lab.eve_path}</span>
            </summary>
            <table>
              <thead><tr><th>Router</th><th>Role</th><th>SSH address</th><th>User</th><th>Password</th><th>Enable secret</th><th>Baseline</th><th /></tr></thead>
              <tbody>
                {rows.map((r) => {
                  const k = `${lab.id}/${r.name}`;
                  return (
                    <tr key={k}>
                      <td><b>{r.name}</b> <span className="muted small">{r.router_id}</span></td>
                      <td>{r.role}</td>
                      <td><code>{r.mgmt_ip}</code></td>
                      <td><code>{r.username}</code></td>
                      <td><Secret value={r.password} shown={all || shown[k + "/p"]} onReveal={() => flip(k + "/p")} /></td>
                      <td><Secret value={r.secret} shown={all || shown[k + "/s"]} onReveal={() => flip(k + "/s")} /></td>
                      <td>
                        {r.baseline_match === true && <span className="badge ok">matches</span>}
                        {r.baseline_match === false && <span className="badge bad">baseline differs</span>}
                        {r.baseline_match == null && <span className="badge muted">no baseline</span>}
                      </td>
                      <td><a className="btn" href={puttyHref(lab.id, r.name)}>SSH session</a></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </details>
        );
      })}
    </>
  );
}
