import { useEffect, useState } from "react";
import { api, usePoll } from "./api.js";

const STATE_CLASS = {
  FULL: "ok", UP: "ok", DR: "ok", BDR: "ok", P2P: "ok",
  "2WAY": "warn", INIT: "warn", EXSTART: "warn", EXCHANGE: "warn", LOADING: "warn", ATTEMPT: "warn", DROTH: "muted", LOOP: "muted",
  DOWN: "bad",
};
const Badge = ({ v }) => <span className={`badge ${STATE_CLASS[String(v).toUpperCase()] || "muted"}`}>{v}</span>;

function Router({ r }) {
  const routes = Object.entries(r.routes || {});
  return (
    <section className={`card ${r.reachable ? "" : "dim"}`}>
      <h3>
        {r.router} <span className="muted small">{r.role}</span>
        <span className="spacer" />
        <Badge v={r.reachable ? "UP" : "DOWN"} />
      </h3>

      <h4>Neighbors</h4>
      <table>
        <thead><tr><th>Neighbor ID</th><th>Interface</th><th>State</th><th>Role</th><th>Pri</th></tr></thead>
        <tbody>
          {r.neighbors.map((n) => (
            <tr key={n.neighbor}>
              <td>{n.neighbor}</td><td>{n.interface}</td><td><Badge v={n.state} /></td><td>{n.role}</td><td>{n.priority}</td>
            </tr>
          ))}
          {!r.neighbors.length && <tr><td colSpan="5" className="muted">none</td></tr>}
        </tbody>
      </table>

      <h4>Interfaces</h4>
      <table>
        <thead><tr><th>Interface</th><th>Area</th><th>Address</th><th>Cost</th><th>State</th><th>Full</th></tr></thead>
        <tbody>
          {r.interfaces.map((i) => (
            <tr key={i.interface}>
              <td>{i.interface}</td><td>{i.area}</td><td>{i.address}</td><td>{i.cost}</td><td><Badge v={i.state} /></td>
              <td>{i.neighbors}/{i.expected}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="chips">
        <span className="muted small">OSPF routes</span>
        {routes.length ? routes.map(([t, c]) => <span key={t} className="chip">{t} × {c}</span>) : <span className="muted small">none</span>}
      </div>
      {(r.bfd || []).map((b) => (
        <div className="chips" key={b.neighbor}><span className="muted small">BFD</span> {b.neighbor} ({b.interface}) <Badge v={b.state} /></div>
      ))}
      {(r.sla || []).map((s) => (
        <div className="chips" key={s.operation}>
          <span className="muted small">IP SLA {s.operation}</span> <Badge v={s.ok ? "UP" : "DOWN"} /> {s.rtt_ms != null ? `${s.rtt_ms} ms` : "no RTT"}
        </div>
      ))}
    </section>
  );
}

function describe(e) {
  switch (e.type) {
    case "neighbor_state_change": return `${e.router}: neighbor ${e.neighbor} (${e.interface}) ${e.prev_state} → ${e.state}`;
    case "neighbor_lost": return `${e.router}: neighbor ${e.neighbor} (${e.interface}) lost (was ${e.prev_state})`;
    case "interface_role_change": return `${e.router}: ${e.interface} ${e.prev_state} → ${e.state} (area ${e.area})`;
    case "router_unreachable": return `${e.router}: unreachable`;
    case "router_reachable": return `${e.router}: reachable again`;
    case "config_change": return `${e.scenario} ${e.mode}: ${e.result}${e.duration != null ? ` in ${e.duration}s` : ""}`;
    default: return JSON.stringify(e);
  }
}

function Events() {
  const [events, setEvents] = useState([]);
  useEffect(() => {
    let alive = true;
    api("/api/events/recent").then((l) => alive && setEvents(l)).catch(() => {});
    const es = new EventSource("/api/events/stream");
    es.addEventListener("ospf", (m) => setEvents((l) => [JSON.parse(m.data), ...l].slice(0, 200)));
    return () => {
      alive = false;
      es.close();
    };
  }, []);
  return (
    <section className="card">
      <h3>Live events <span className="muted small">Kafka topics ospf.neighbor.events / ospf.config.changes</span></h3>
      <ul className="events">
        {events.map((e) => (
          <li key={e.event_id} className={e.severity || ""}>
            <time>{new Date(e.ts).toLocaleTimeString()}</time> {describe(e)}
          </li>
        ))}
        {!events.length && <li className="muted">No events yet: they appear when a neighbor, DR/BDR role or config changes.</li>}
      </ul>
    </section>
  );
}

export default function Monitor() {
  const { data, error } = usePoll("/api/monitor/state", 5000);
  return (
    <>
      {error && <div className="alert bad">Backend: {error}</div>}
      {data && !data.length && <div className="alert">No snapshot yet. The monitor publishes one every poll interval once the routers answer SSH.</div>}
      <div className="grid">{(data || []).map((r) => <Router key={r.router} r={r} />)}</div>
      <Events />
    </>
  );
}
