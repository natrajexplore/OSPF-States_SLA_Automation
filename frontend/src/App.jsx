import { useState } from "react";
import { usePoll } from "./api.js";
import Monitor from "./Monitor.jsx";
import Scenarios from "./Scenarios.jsx";
import Lab from "./Lab.jsx";

const TABS = [
  ["monitor", "Monitor"],
  ["scenarios", "Scenarios"],
  ["lab", "Lab"],
];

export default function App() {
  const [tab, setTab] = useState(() => location.hash.slice(1) || "monitor");
  const { data: cfg } = usePoll("/api/config", 30000);
  const go = (t) => {
    setTab(t);
    location.hash = t;
  };
  return (
    <>
      <header>
        <h1>OSPF SLA &amp; States</h1>
        <nav>
          {TABS.map(([id, label]) => (
            <button key={id} className={tab === id ? "on" : ""} onClick={() => go(id)}>
              {label}
            </button>
          ))}
        </nav>
        <span className="spacer" />
        {cfg?.grafana_url && (
          <a className="btn" href={cfg.grafana_url} target="_blank" rel="noreferrer">
            Grafana ↗
          </a>
        )}
        {cfg && <span className="muted small">{cfg.kafka_enabled ? "Kafka on" : "Kafka off"} · poll {cfg.poll_interval}s</span>}
      </header>
      <main>
        {tab === "monitor" && <Monitor />}
        {tab === "scenarios" && <Scenarios />}
        {tab === "lab" && <Lab cfg={cfg} />}
      </main>
    </>
  );
}
