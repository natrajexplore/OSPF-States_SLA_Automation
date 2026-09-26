import { useEffect, useRef, useState } from "react";
import { api, usePoll } from "./api.js";
import { puttyHref } from "./liveState.js";

// Read-only CLI: any whitelisted `show` on one router, through GET /api/devices/{name}/show (the backend refuses anything
// else). Opened from the Live tab's "CLI tab" button as #cli/<router>, which also runs `show ip ospf neighbor`.
const COMMANDS = [
  "show ip ospf neighbor",
  "show ip ospf interface brief",
  "show ip ospf",
  "show ip route ospf",
  "show ip ospf database",
  "show ip ospf database summary",
  "show ip ospf database external",
  "show ip ospf database nssa-external",
  "show ip ospf border-routers",
  "show ip ospf interface Ethernet1/0",
  "show ip ospf interface Ethernet1/1",
  "show ip route 10.255.0.1",
  "show ip sla statistics",
  "show running-config | section router ospf",
];
const transcripts = {};                     // router -> [{cmd, out, err, at}], kept while the page is open

export default function Cli({ router: initial }) {
  const { data: devices } = usePoll("/api/devices", 15000);
  const { data: monitor } = usePoll("/api/monitor/state", 10000);
  const [router, setRouter] = useState(initial || null);
  const [cmd, setCmd] = useState(COMMANDS[0]);
  const [busy, setBusy] = useState(false);
  const [, bump] = useState(0);
  const pre = useRef(null);
  const autoRan = useRef(false);

  const names = (devices || []).map((d) => d.name);
  useEffect(() => { if (!router && names.length) setRouter(names[0]); }, [router, names.join()]);
  useEffect(() => { if (initial) setRouter(initial); }, [initial]);

  const run = async (c = cmd, r = router) => {
    if (!r || !c.trim()) return;
    setBusy(true);
    const entry = { cmd: c.trim(), at: new Date().toLocaleTimeString() };
    try {
      entry.out = (await api(`/api/devices/${encodeURIComponent(r)}/show?cmd=${encodeURIComponent(c.trim())}`)).output;
    } catch (e) {
      entry.err = e.message;
    }
    (transcripts[r] ||= []).push(entry);
    setBusy(false);
    bump((x) => x + 1);
  };

  // arriving through "CLI tab" (#cli/R3): answer right away
  useEffect(() => {
    if (initial && !autoRan.current) { autoRan.current = true; run("show ip ospf neighbor", initial); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial]);
  useEffect(() => { pre.current && (pre.current.scrollTop = pre.current.scrollHeight); });

  const lines = transcripts[router] || [];
  const text = lines.map((l) => `${router}# ${l.cmd}    (${l.at})\n${l.err ? `% ${l.err}` : l.out}`).join("\n\n");
  const reach = Object.fromEntries((monitor || []).map((m) => [m.router, m.reachable]));
  const dev = (devices || []).find((d) => d.name === router);

  return (
    <>
      <section className="card">
        <h3>
          CLI
          <span className="muted small">read-only `show` commands over SSH, through the backend</span>
          <span className="spacer" />
          {dev && <a className="btn" href={puttyHref("shared", dev.name)} title="Open this router in its own PuTTY window (one-time scripts\putty-setup.ps1)">SSH session (PuTTY)</a>}
        </h3>
        <div className="chips">
          {names.map((n) => (
            <button key={n} className={n === router ? "" : "secondary"} onClick={() => setRouter(n)}>
              <span className={`dot ${reach[n] === true ? "ok" : reach[n] === false ? "bad" : ""}`} />{n}
            </button>
          ))}
        </div>
        <form className="cli-form" onSubmit={(e) => { e.preventDefault(); run(); }}>
          <span className="cli-prompt">{router || "?"}#</span>
          <input list="cli-cmds" value={cmd} onChange={(e) => setCmd(e.target.value)} spellCheck={false} aria-label="show command" />
          <datalist id="cli-cmds">{COMMANDS.map((c) => <option key={c} value={c} />)}</datalist>
          <button disabled={busy || !router}>{busy ? "Running…" : "Run"}</button>
        </form>
        <div className="chips">
          {COMMANDS.slice(0, 6).map((c) => (
            <button key={c} className="secondary small" disabled={busy || !router} onClick={() => { setCmd(c); run(c); }}>{c.replace("show ", "")}</button>
          ))}
        </div>
        <p className="muted small">
          Allowed: <code>show ip ospf …</code>, <code>show ip route …</code>, <code>show ip sla statistics</code>, <code>show bfd neighbors</code>,
          <code>show running-config | section router ospf</code>. Anything else is refused by the backend. For configuration, use a PuTTY session.
          {dev && <> SSH address <code>{dev.mgmt_ip}</code>.</>}
        </p>
      </section>
      <section className="card">
        <h3>
          {router} transcript <span className="muted small">{lines.length} command{lines.length === 1 ? "" : "s"}</span>
          <span className="spacer" />
          <button className="secondary" disabled={!lines.length} onClick={() => navigator.clipboard?.writeText(text)}>Copy</button>
          <button className="secondary" disabled={!lines.length} onClick={() => { transcripts[router] = []; bump((x) => x + 1); }}>Clear</button>
        </h3>
        <pre className="console cli-out" ref={pre}>{text || "No commands yet. Pick one above."}</pre>
      </section>
    </>
  );
}
