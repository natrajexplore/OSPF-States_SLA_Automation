import { useEffect, useState } from "react";
import { api } from "./api.js";

function describe(topic, v) {
  if (topic.endsWith("snapshots")) {
    if (!v || typeof v !== "object") return "-";
    const full = (v.neighbors || []).filter((n) => n.full).length;
    return `${v.router}: ${v.reachable === false ? "unreachable" : `${full}/${(v.neighbors || []).length} neighbors FULL`}`;
  }
  switch (v?.type) {
    case "neighbor_state_change": return `${v.router}: neighbor ${v.neighbor} (${v.interface}) ${v.prev_state} → ${v.state}`;
    case "neighbor_lost": return `${v.router}: neighbor ${v.neighbor} (${v.interface}) lost (was ${v.prev_state})`;
    case "interface_role_change": return `${v.router}: ${v.interface} ${v.prev_state} → ${v.state} (area ${v.area})`;
    case "router_unreachable": return `${v.router}: unreachable`;
    case "router_reachable": return `${v.router}: reachable again`;
    case "config_change": return `${v.scenario} ${v.mode}: ${v.result}${v.duration != null ? ` in ${v.duration}s` : ""}`;
    default: return v ? JSON.stringify(v).slice(0, 160) : "-";
  }
}

const SHORT = { "ospf.neighbor.events": "events", "ospf.neighbor.snapshots": "snapshots", "ospf.config.changes": "config" };

export default function Kafka({ cfg }) {
  const [topics, setTopics] = useState([]);
  const [counts, setCounts] = useState({});
  const [messages, setMessages] = useState([]);
  const [connected, setConnected] = useState(false);
  const [filter, setFilter] = useState(null);

  useEffect(() => {
    let alive = true;
    api("/api/kafka/recent").then((d) => {
      if (!alive) return;
      setTopics(d.topics || []);
      setCounts(d.counts || {});
      setMessages(d.messages || []);
    }).catch(() => {});
    const es = new EventSource("/api/kafka/stream");
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    es.addEventListener("kafka", (m) => {
      const item = JSON.parse(m.data);
      setMessages((l) => [item, ...l].slice(0, 300));
      setCounts((c) => ({ ...c, [item.topic]: (c[item.topic] || 0) + 1 }));
    });
    return () => {
      alive = false;
      es.close();
    };
  }, []);

  const shown = filter ? messages.filter((m) => m.topic === filter) : messages;

  return (
    <>
      <section className="card">
        <h3>
          Kafka
          <span className={`badge ${connected ? "ok" : "warn"}`}>{connected ? "live" : "connecting"}</span>
          <span className="spacer" />
          {cfg?.kafka_ui_url && (
            <a className="btn" href={cfg.kafka_ui_url} target="_blank" rel="noreferrer">
              Open in Kafka UI {"↗"}
            </a>
          )}
        </h3>
        <p className="muted small">
          Live tail of the 3 OSPF Kafka topics, read straight from the broker (not the in-process UI event feed on the
          Monitor tab - this is the same pipeline the exporter/Prometheus consume from). A fresh consumer group starts
          from "latest" on backend restart, so history resets then; this is a live view, not an archive.
        </p>
        <div className="chips">
          <button className={filter === null ? "" : "secondary"} onClick={() => setFilter(null)}>
            all ({Object.values(counts).reduce((a, b) => a + b, 0)})
          </button>
          {topics.map((t) => (
            <button key={t} className={filter === t ? "" : "secondary"} onClick={() => setFilter(t)}>
              {SHORT[t] || t} ({counts[t] || 0})
            </button>
          ))}
        </div>
      </section>
      <section className="card">
        <table>
          <thead><tr><th>Time</th><th>Topic</th><th>Key</th><th>Message</th></tr></thead>
          <tbody>
            {shown.map((m, i) => (
              <tr key={i}>
                <td className="muted small">{m.value?.ts ? new Date(m.value.ts).toLocaleTimeString() : "-"}</td>
                <td><span className="chip">{SHORT[m.topic] || m.topic}</span></td>
                <td className="muted small">{m.key || "-"}</td>
                <td>
                  {describe(m.topic, m.value)}
                  <details>
                    <summary className="muted small">raw</summary>
                    <pre className="small">{JSON.stringify(m.value, null, 2)}</pre>
                  </details>
                </td>
              </tr>
            ))}
            {!shown.length && (
              <tr><td colSpan={4} className="muted">
                No messages yet. They appear as the poller runs (every OSPF_POLL_INTERVAL seconds) or a scenario applies/rolls back.
              </td></tr>
            )}
          </tbody>
        </table>
      </section>
    </>
  );
}
