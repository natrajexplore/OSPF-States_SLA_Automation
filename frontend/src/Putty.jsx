import { useState } from "react";
import { usePoll } from "./api.js";
import { puttyHref, watchPuttyLaunch } from "./liveState.js";

// PuTTY login to every router. In simulation mode the routers are SSH servers in the backend (127.0.0.1:2201-2204, a small
// IOS CLI on the same simulated lab the dashboard drives); on the real lab they are the routers' management addresses,
// reached through the EVE-NG VM. GET /api/putty lists the sessions; scripts/putty-setup.ps1 saves them in PuTTY once and
// registers the ospfputty: link that "Open in PuTTY" uses.

function Copy({ text, label = "Copy" }) {
  const [done, setDone] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1200); }).catch(() => {});
  };
  return <button className="secondary small" onClick={copy} title={text}>{done ? "Copied" : label}</button>;
}

const puttyCmd = (s) => s.jump
  ? `putty.exe -load "OSPF ${s.lab} ${s.router}"`
  : `putty.exe -ssh ${s.host} -P ${s.port}`;       // no user: PuTTY asks "login as:"

const sshCmd = (s, jumpUser = "root") => s.jump
  ? `ssh -J ${jumpUser}@${s.jump} -o KexAlgorithms=+diffie-hellman-group14-sha1 -o HostKeyAlgorithms=+ssh-rsa ${s.username}@${s.host}`
  : `ssh -p ${s.port} ${s.username}@${s.host}`;

const TRY = [
  ["show ip ospf neighbor", "the adjacencies, as on the Lab tab"],
  ["conf t", "configuration mode (Ctrl-Z or end to leave)"],
  ["interface e1/1", "R3-R4 link (on R3)"],
  ["ip ospf hello-interval 5", "timer mismatch: R3-R4 drops in the 3D view and in Grafana"],
  ["no ip ospf hello-interval", "and it comes back"],
  ["sh ip ospf int e1/1 | inc Hello", "abbreviations and | include work"],
];

export default function Putty({ sim }) {
  const { data, error } = usePoll("/api/putty", 30000);
  const [show, setShow] = useState(false);
  const [q, setQ] = useState("");
  const sessions = data?.sessions || [];
  const setup = `powershell -ExecutionPolicy Bypass -File scripts\\putty-setup.ps1 -Server ${location.origin}`;
  const needle = q.trim().toLowerCase();
  const rows = sessions.filter((s) => !needle || [s.lab, s.router, s.host].some((v) => String(v).toLowerCase().includes(needle)));
  const labs = [...new Set(rows.map((s) => s.lab))];
  const isSim = data ? data.mode === "simulation" : sim;

  return (
    <>
      {error && <div className="alert bad">Backend: {error}</div>}
      <section className="card">
        <h3>
          PuTTY login
          <span className="muted small">
            {isSim ? "simulated routers, SSH on this PC" : "real routers, through the EVE-NG VM"} · {sessions.length} sessions
          </span>
          <span className="spacer" />
          {sessions.length > 8 && <input className="filter" placeholder="Filter: lab, router…" value={q} onChange={(e) => setQ(e.target.value)} />}
          <button className="secondary" onClick={() => setShow(!show)}>{show ? "Hide passwords" : "Show passwords"}</button>
        </h3>
        {data && !data.enabled && (
          <div className="alert bad">SSH login to the simulated routers is turned off (<code>OSPF_SIM_SSH=false</code> on the backend).</div>
        )}
        <ol className="steps">
          <li>
            <b>Once on this PC</b>, from the repository folder in PowerShell. It saves one PuTTY session per router and lets the
            buttons below start PuTTY (your Windows user only; <code>-Uninstall</code> removes it). Run it again after switching
            between simulation and the real lab.
            <div className="cmdline"><code>{setup}</code><Copy text={setup} /></div>
          </li>
          <li>
            <b>Open in PuTTY</b> on a router (the browser asks once to allow <code>ospfputty:</code> links). Without the setup, paste
            the PuTTY or ssh command instead.
          </li>
          <li>
            PuTTY asks <code>login as:</code> type <code>{sessions[0]?.username || "cisco"}</code>, then the password
            (<code>{show ? sessions[0]?.password || "lab123" : "••••••"}</code>). The user has privilege 15, so the prompt is
            {" "}<code>R1#</code>; after <code>disable</code>, <code>enable</code> asks for the enable secret.
            {isSim && data?.fingerprint && <> The setup trusts the routers' host key (<code>{data.fingerprint}</code>), so there is no security alert.</>}
          </li>
        </ol>
        {isSim ? (
          <p className="muted small">
            The simulated routers answer on <code>127.0.0.1</code> only. What you type changes the same model the dashboard uses, so
            the Lab tab, the monitor and Grafana show it, and Apply / Rollback on the dashboard shows up in PuTTY.
          </p>
        ) : (
          <p className="muted small">
            The routers' addresses (192.168.99.x) only exist inside the EVE-NG VM, so PuTTY goes through it with the Windows OpenSSH
            client: the VM must be running and accept key login from this PC. All standalone labs share the same addresses, so only
            the lab that is running answers.
          </p>
        )}
      </section>

      {labs.map((lab) => (
        <details className="card" key={lab} open={lab === "sim" || lab === "shared" || !!needle}>
          <summary><b>{lab === "sim" ? "Simulated lab" : lab}</b> <span className="muted small">{rows.filter((s) => s.lab === lab).length} routers</span></summary>
          <table>
            <thead><tr><th>Router</th><th>Address</th><th>User</th><th>Password</th><th>Enable secret</th><th /></tr></thead>
            <tbody>
              {rows.filter((s) => s.lab === lab).map((s) => (
                <tr key={`${s.lab}/${s.router}`}>
                  <td><b>{s.router}</b></td>
                  <td><code>{s.host}{s.port !== 22 ? `:${s.port}` : ""}</code>{s.jump && <span className="muted small"> via {s.jump}</span>}</td>
                  <td><code>{s.username}</code></td>
                  <td><code>{show ? s.password : "••••••"}</code> <Copy text={s.password} /></td>
                  <td><code>{show ? s.secret : "••••••"}</code> <Copy text={s.secret} /></td>
                  <td className="actions">
                    <a onClick={watchPuttyLaunch} className="btn small" href={puttyHref(s.lab, s.router)} title={`Opens the saved PuTTY session "OSPF ${s.lab} ${s.router}"`}>Open in PuTTY</a>
                    <Copy text={puttyCmd(s)} label="PuTTY cmd" />
                    <Copy text={sshCmd(s)} label="ssh cmd" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ))}

      {isSim && (
        <section className="card">
          <h3>Try it <span className="muted small">on R3</span></h3>
          <table>
            <tbody>
              {TRY.map(([c, what]) => <tr key={c}><td><code>{c}</code></td><td className="muted small">{what}</td></tr>)}
            </tbody>
          </table>
          <p className="muted small">Type <code>?</code> for the commands the simulator knows. <b>Reset lab to baseline</b> on the Lab tab undoes everything.</p>
        </section>
      )}
    </>
  );
}
