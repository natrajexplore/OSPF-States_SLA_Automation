import { useEffect, useState } from "react";
import { api } from "./api.js";

const QUERIES = {
  reachable: "ospf_router_reachable",
  neighbors: "ospf_neighbor_full",
  cost: "ospf_interface_cost",
  slaRtt: "ospf_sla_rtt_milliseconds",
  slaUp: "ospf_sla_up",
  bfdUp: "ospf_bfd_up",
  transitions: "sum(ospf_neighbor_transitions_total)",
  configChanges: "sum(ospf_config_changes_total)",
  lost: "sum(ospf_neighbor_lost_total)",
};

function usePromQueries(ms = 10000) {
  const [data, setData] = useState({});
  const [error, setError] = useState(null);
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const entries = await Promise.all(
          Object.entries(QUERIES).map(async ([key, q]) => {
            const r = await api(`/api/prometheus/query?query=${encodeURIComponent(q)}`);
            return [key, r.data?.result || []];
          })
        );
        if (alive) {
          setData(Object.fromEntries(entries));
          setError(null);
        }
      } catch (e) {
        if (alive) setError(e.message);
      }
    };
    tick();
    const id = setInterval(tick, ms);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [ms]);
  return { data, error };
}

const num = (r) => (r ? Number(r.value[1]) : null);
const byLabel = (rows, key) => Object.fromEntries((rows || []).map((r) => [r.metric[key], Number(r.value[1])]));

function Stat({ label, value }) {
  return (
    <div className="chips">
      <span className="muted small">{label}</span> <span className="chip">{value ?? "-"}</span>
    </div>
  );
}

export default function Prometheus({ cfg }) {
  const { data, error } = usePromQueries();

  const rtt = byLabel(data.slaRtt, "router");
  const slaUp = byLabel(data.slaUp, "router");
  const reach = byLabel(data.reachable, "router");

  return (
    <>
      <section className="card">
        <h3>
          Prometheus
          <span className="spacer" />
          {cfg?.prometheus_url && (
            <a className="btn" href={cfg.prometheus_url} target="_blank" rel="noreferrer">
              Open in Prometheus {"↗"}
            </a>
          )}
          {cfg?.grafana_url && (
            <a className="btn secondary" href={cfg.grafana_url} target="_blank" rel="noreferrer">
              Open in Grafana {"↗"}
            </a>
          )}
        </h3>
        <p className="muted small">
          Live PromQL queries against the same Prometheus instance Grafana reads from (proxied through the backend -
          the browser never talks to Prometheus directly). Refreshes every 10s.
        </p>
        {error && <div className="alert bad">Prometheus: {error}</div>}
        <div className="chips">
          <Stat label="Neighbor transitions (total)" value={num(data.transitions?.[0])} />
          <Stat label="Neighbors lost (total)" value={num(data.lost?.[0])} />
          <Stat label="Config pushes (total)" value={num(data.configChanges?.[0])} />
        </div>
      </section>

      <section className="card">
        <h3>Router reachability</h3>
        <table>
          <thead><tr><th>Router</th><th>Reachable</th><th>IP SLA RTT</th><th>IP SLA up</th></tr></thead>
          <tbody>
            {Object.keys(reach).length === 0 && (
              <tr><td colSpan={4} className="muted">No data yet - the exporter needs at least one poll cycle after startup.</td></tr>
            )}
            {Object.entries(reach).map(([router, up]) => (
              <tr key={router}>
                <td>{router}</td>
                <td><span className={`badge ${up ? "ok" : "bad"}`}>{up ? "up" : "down"}</span></td>
                <td>{rtt[router] != null ? `${rtt[router]} ms` : "-"}</td>
                <td>{router in slaUp ? <span className={`badge ${slaUp[router] ? "ok" : "bad"}`}>{slaUp[router] ? "ok" : "fail"}</span> : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h3>Neighbor adjacencies (ospf_neighbor_full)</h3>
        <table>
          <thead><tr><th>Router</th><th>Neighbor</th><th>Interface</th><th>State</th></tr></thead>
          <tbody>
            {(data.neighbors || []).map((r, i) => (
              <tr key={i}>
                <td>{r.metric.router}</td><td>{r.metric.neighbor}</td><td>{r.metric.interface}</td>
                <td><span className={`badge ${Number(r.value[1]) ? "ok" : "bad"}`}>{Number(r.value[1]) ? "FULL" : "not full"}</span></td>
              </tr>
            ))}
            {!(data.neighbors || []).length && <tr><td colSpan={4} className="muted">No series yet.</td></tr>}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h3>Interface cost (ospf_interface_cost)</h3>
        <table>
          <thead><tr><th>Router</th><th>Interface</th><th>Area</th><th>Cost</th></tr></thead>
          <tbody>
            {(data.cost || []).map((r, i) => (
              <tr key={i}>
                <td>{r.metric.router}</td><td>{r.metric.interface}</td><td>{r.metric.area}</td><td>{r.value[1]}</td>
              </tr>
            ))}
            {!(data.cost || []).length && <tr><td colSpan={4} className="muted">No series yet.</td></tr>}
          </tbody>
        </table>
      </section>

      {(data.bfdUp || []).length > 0 && (
        <section className="card">
          <h3>BFD (ospf_bfd_up)</h3>
          <table>
            <thead><tr><th>Router</th><th>Neighbor</th><th>Interface</th><th>State</th></tr></thead>
            <tbody>
              {data.bfdUp.map((r, i) => (
                <tr key={i}>
                  <td>{r.metric.router}</td><td>{r.metric.neighbor}</td><td>{r.metric.interface}</td>
                  <td><span className={`badge ${Number(r.value[1]) ? "ok" : "bad"}`}>{Number(r.value[1]) ? "Up" : "Down"}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}
