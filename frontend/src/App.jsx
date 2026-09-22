import { useState } from "react";
import { usePoll } from "./api.js";
import Monitor from "./Monitor.jsx";
import Scenarios from "./Scenarios.jsx";
import Lab from "./Lab.jsx";
import Learn from "./Learn.jsx";
import Kafka from "./Kafka.jsx";
import Prometheus from "./Prometheus.jsx";

const TABS = [
  ["monitor", "Monitor"],
  ["scenarios", "Scenarios"],
  ["lab", "Lab"],
  ["learn", "Learn"],
  ["kafka", "Kafka"],
  ["prometheus", "Prometheus"],
];

export default function App() {
  const [tab, setTab] = useState(() => location.hash.slice(1) || "monitor");
  const [scenarioFocus, setScenarioFocus] = useState(null);
  const { data: cfg } = usePoll("/api/config", 30000);
  const go = (t) => {
    setTab(t);
    location.hash = t;
  };
  const goToScenarios = (sid) => {
    setScenarioFocus(sid);
    go("scenarios");
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
        {tab === "scenarios" && <Scenarios focus={scenarioFocus} />}
        {tab === "lab" && <Lab cfg={cfg} />}
        {tab === "learn" && <Learn goToScenarios={goToScenarios} />}
        {tab === "kafka" && <Kafka cfg={cfg} />}
        {tab === "prometheus" && <Prometheus cfg={cfg} />}
      </main>
    </>
  );
}
