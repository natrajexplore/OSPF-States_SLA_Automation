import { useEffect, useMemo, useRef, useState } from "react";
import { usePoll, useRun } from "./api.js";
import { liveState, puttyHref } from "./liveState.js";
import RunPanel from "./RunPanel.jsx";
import Topo3D from "./Topo3D.jsx";

// The run log (scenarios.py) as the SSH sessions really type it: one session per router, each line at the prompt of its
// config mode, then `end` and `write memory` (push_config saves). The before/after checks are separate read-only sessions.
const SUBMODE = [[/^interface /, "config-if"], [/^router /, "config-router"], [/^route-map /, "config-route-map"], [/^ip sla \d/, "config-ip-sla"]];

export function sshTranscript(lines, nodes) {
  const byName = Object.fromEntries((nodes || []).map((n) => [n.name, n]));
  const out = [];
  let open = null, mode = "";
  const close = () => {
    if (!open) return;
    out.push({ r: open, kind: "cfg", text: `${open}(${mode || "config"})#end` }, { r: open, kind: "exec", text: `${open}#write memory` });
    open = null;
  };
  for (const raw of lines) {
    let m;
    if ((m = raw.match(/^\s+(\S+)\| (.*)$/)) && m[1] === open) {
      const [, r, ln] = m;
      const indented = /^\s/.test(ln);
      out.push({ r, kind: "cfg", text: `${r}(${indented && mode ? mode : "config"})#${ln.trim()}` });
      if (!indented) mode = (SUBMODE.find(([re]) => re.test(ln)) || [null, ""])[1];
      continue;
    }
    close();
    if ((m = raw.match(/^--- pushing to (\S+) ---$/))) {
      const n = byName[m[1]];
      open = m[1]; mode = "";
      out.push({ r: open, kind: "ssh", text: `$ ssh ${n?.username || "lab"}@${n?.mgmt_ip || m[1]}` },
        { r: open, kind: "exec", text: `${open}#configure terminal` });
    } else if ((m = raw.match(/^--- (.+) on (\S+) ---$/))) {
      out.push({ r: m[2], kind: "exec", text: `${m[2]}#${m[1]}` });
    } else if ((m = raw.match(/^\[(before|after)\] (\S+) :: (.+?)( FAILED: .*)?$/))) {
      out.push({ r: m[2], kind: m[4] ? "err" : "show", text: `${m[2]}#${m[3]}`, note: `${m[1]} check${m[4] ? m[4] : ""}` });
    } else if (raw.startsWith("ERROR")) {
      out.push({ r: null, kind: "err", text: raw });
    }
  }
  close();
  return out;
}

export default function Live({ goToCli }) {
  const { data: graph, error: gErr } = usePoll("/api/graph", 300000);
  const { data: monitor } = usePoll("/api/monitor/state", 5000);
  const { data: devices } = usePoll("/api/devices", 15000);
  const { data: scenarios } = usePoll("/api/scenarios", 300000);
  const [sid, setSid] = useState("");
  const [mode, setMode] = useState(null);
  const [sel, setSel] = useState(null);
  const [filter, setFilter] = useState("all");
  const r = useRun();
  const eng = useRef(null);
  const seen = useRef(0);
  const box = useRef(null);

  const sc = (scenarios || []).find((s) => s.id === sid);
  useEffect(() => { if (!sid && scenarios?.length) setSid(scenarios[0].id); }, [scenarios, sid]);
  const state = useMemo(() => liveState(graph, monitor, devices), [graph, monitor, devices]);
  const transcript = useMemo(() => sshTranscript(r.lines, graph?.nodes), [r.lines, graph]);

  // animate each new transcript entry: a session starts = pulse, a config line = SSH beam, a check = small beam
  useEffect(() => {
    if (transcript.length < seen.current) seen.current = 0;              // a new run started
    const v = eng.current;
    transcript.slice(seen.current).forEach((t) => {
      if (!v || !t.r) return;
      if (t.kind === "ssh") v.pulse(t.r);
      else if (t.kind === "cfg" || t.kind === "show" || t.kind === "exec") v.beam(t.r);
    });
    seen.current = transcript.length;
    if (box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [transcript]);

  const go = (m) => { setMode(m); seen.current = 0; r.start(`/api/scenarios/${sid}/${m === "apply" ? "run" : "rollback"}`); };
  const mon = Object.fromEntries((monitor || []).map((m) => [m.router, m]));
  const eve = Object.fromEntries((devices || []).map((d) => [d.name, d]));
  const shown = transcript.filter((t) => filter === "all" || t.r === filter || !t.r);
  const text = shown.map((t) => t.text + (t.note ? `      ! ${t.note}` : "")).join("\n");

  return (
    <>
      {gErr && <div className="alert bad">Backend: {gErr}</div>}
      <section className="card">
        <h3>
          Live lab
          <span className="muted small">{graph ? `${graph.lab} · ${graph.nodes.length} routers · monitor every 5 s` : "loading…"}</span>
          <span className="spacer" />
          <select value={sid} onChange={(e) => setSid(e.target.value)} aria-label="scenario">
            {(scenarios || []).map((s) => <option key={s.id} value={s.id}>{s.id}: {s.title.split(" - ")[0]}</option>)}
          </select>
          <button disabled={r.busy || !sid} onClick={() => go("apply")}>Apply</button>
          <button className="secondary" disabled={r.busy || !sid} onClick={() => go("rollback")}>Rollback</button>
        </h3>
        {sc && <p className="muted small">{sc.summary} <b>Configures:</b> {sc.targets.join(", ")} (amber in 3D).</p>}
        <div className="legend small">
          <span><i style={{ background: "#3fb950" }} />adjacency FULL / router answers</span>
          <span><i style={{ background: "#d29922" }} />adjacency forming (INIT, EXSTART…)</span>
          <span><i style={{ background: "#f85149" }} />neighbor lost / router unreachable</span>
          <span><i style={{ background: "#5b6b7c" }} />no data yet</span>
          <span><i style={{ background: "#fbbf24" }} />configured by the scenario</span>
          <span><i style={{ background: "#a371f7" }} />SSH executor → router</span>
        </div>
      </section>

      <div className="live-grid">
        <section className="card">
          <Topo3D graph={graph} state={state} highlight={sc?.targets} onSelect={(n) => { setSel(n); setFilter(n); }}
            onReady={(v) => (eng.current = v)} height={500} />
          <p className="muted small">Drag to orbit, scroll to zoom, click a router to filter the SSH / CLI panel to it.</p>
        </section>

        <section className="card">
          <h3>EVE-NG and SSH</h3>
          <table>
            <thead><tr><th>Router</th><th>EVE-NG</th><th>SSH address</th><th>OSPF</th><th /></tr></thead>
            <tbody>
              {(graph?.nodes || []).map((n) => {
                const m = mon[n.name], nb = m?.neighbors || [];
                const full = nb.filter((x) => x.full).length;
                const st = eve[n.name]?.status || "unknown";
                return (
                  <tr key={n.name} className={sel === n.name ? "sel" : ""} onClick={() => setSel(n.name)}>
                    <td><b>{n.name}</b><div className="muted small">{n.router_id}</div></td>
                    <td><span className={`badge ${st === "running" ? "ok" : st === "stopped" ? "bad" : "muted"}`}>{st}</span></td>
                    <td><code>{n.mgmt_ip}</code><div className="muted small">{m ? (m.reachable ? "answers" : "no answer") : "not polled yet"}</div></td>
                    <td>{m ? `${full}/${nb.length} FULL` : "-"}</td>
                    <td className="nowrap">
                      <a className="btn small" href={puttyHref("shared", n.name)} title="Own PuTTY window (one-time scripts\putty-setup.ps1)">SSH session</a>{" "}
                      <button className="secondary small" onClick={() => goToCli(n.name)} title="Open the CLI tab on this router and run show ip ospf neighbor">CLI tab</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="muted small">
            Routers accept SSH only (<code>transport input ssh</code>). The addresses live inside the EVE VM, so PuTTY goes through the VM
            (<code>scripts\putty-setup.ps1</code>). Login and passwords: Credentials tab. Terminal alternative:{" "}
            <code>ssh -J root@&lt;eve-vm&gt; -o KexAlgorithms=+diffie-hellman-group14-sha1 -o HostKeyAlgorithms=+ssh-rsa lab@{graph?.nodes?.find((n) => n.name === (sel || "R1"))?.mgmt_ip || "192.168.99.11"}</code>
          </p>
        </section>
      </div>

      <section className="card">
        <h3>
          SSH / CLI <span className="muted small">the commands of the last run, per router, as typed</span>
          <span className="spacer" />
          {["all", ...(graph?.nodes || []).map((n) => n.name)].map((f) => (
            <button key={f} className={filter === f ? "" : "secondary"} onClick={() => setFilter(f)}>{f === "all" ? "All" : f}</button>
          ))}
          <button className="secondary" disabled={!text} onClick={() => navigator.clipboard?.writeText(text)}>Copy</button>
        </h3>
        <pre className="console ssh" ref={box}>
          {shown.length ? shown.map((t, i) => (
            <div key={i} className={`t-${t.kind}`}>{t.text}{t.note && <span className="muted">      ! {t.note}</span>}</div>
          )) : "Apply or roll back a scenario to see its SSH sessions here. Read any router with the CLI tab."}
        </pre>
      </section>

      {mode && <RunPanel title={`${sid} · ${mode}`} {...r} />}
    </>
  );
}
