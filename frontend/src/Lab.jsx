import { usePoll, useRun } from "./api.js";
import RunPanel from "./RunPanel.jsx";

const STATUS = { running: "ok", stopped: "bad", starting: "warn" };

export default function Lab({ cfg }) {
  const { data: devices, error } = usePoll("/api/devices", 15000);
  const r = useRun();
  const reset = () => {
    if (window.confirm("Push the baseline configuration to all routers? Scenario changes will be overwritten.")) {
      r.start("/api/lab/reset");
    }
  };
  return (
    <>
      {error && <div className="alert bad">Backend: {error}</div>}
      <section className="card">
        <h3>
          Routers
          <span className="spacer" />
          <button className="danger" disabled={r.busy} onClick={reset}>Reset lab to baseline</button>
        </h3>
        <table>
          <thead><tr><th>Name</th><th>Role</th><th>Router ID</th><th>MGMT IP</th><th>EVE-NG</th><th>Console</th></tr></thead>
          <tbody>
            {(devices || []).map((d) => (
              <tr key={d.name}>
                <td>{d.name}</td><td>{d.role}</td><td>{d.router_id}</td><td>{d.mgmt_ip}</td>
                <td><span className={`badge ${STATUS[d.status] || "muted"}`}>{d.status}</span></td>
                <td>{d.console ? <code>telnet {d.console.replace(":", " ")}</code> : <span className="muted">-</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted small">
          Status and console ports come from the EVE-NG API; if they are empty, check OSPF_EVENG_URL and OSPF_LAB_PATH in .env.
        </p>
      </section>
      <RunPanel title="Reset lab to baseline" {...r} />
      {cfg?.grafana_url && (
        <section className="card">
          <h3>Grafana</h3>
          <a href={cfg.grafana_url} target="_blank" rel="noreferrer">{cfg.grafana_url}</a>
        </section>
      )}
    </>
  );
}
