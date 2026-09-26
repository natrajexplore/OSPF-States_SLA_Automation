import { useEffect, useState } from "react";
import { usePoll } from "./api.js";
import Monitor from "./Monitor.jsx";
import Live from "./Live.jsx";
import Scenarios from "./Scenarios.jsx";
import Cli from "./Cli.jsx";
import Lab from "./Lab.jsx";
import Credentials from "./Credentials.jsx";
import Learn from "./Learn.jsx";
import Kafka from "./Kafka.jsx";
import Prometheus from "./Prometheus.jsx";

const TABS = [
  ["monitor", "Monitor"],
  ["live", "Live 3D"],
  ["scenarios", "Scenarios"],
  ["cli", "CLI"],
  ["lab", "Lab"],
  ["credentials", "Credentials"],
  ["learn", "Learn"],
  ["kafka", "Kafka"],
  ["prometheus", "Prometheus"],
];

// #tab or #tab/arg (for example #cli/R3)
const parseHash = () => {
  const [t, arg] = location.hash.slice(1).split("/");
  return { tab: TABS.some(([id]) => id === t) ? t : "monitor", arg: arg || null };
};

export default function App() {
  const [route, setRoute] = useState(parseHash);
  const [scenarioFocus, setScenarioFocus] = useState(null);
  const { data: cfg } = usePoll("/api/config", 30000);
  useEffect(() => {
    const on = () => setRoute(parseHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const go = (t, arg) => {
    location.hash = arg ? `${t}/${arg}` : t;
    setRoute({ tab: t, arg: arg || null });
  };
  const goToScenarios = (sid) => {
    setScenarioFocus(sid);
    go("scenarios");
  };
  const { tab, arg } = route;
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
        {tab === "live" && <Live goToCli={(r) => go("cli", r)} />}
        {tab === "scenarios" && <Scenarios focus={scenarioFocus} />}
        {tab === "cli" && <Cli router={arg} key={arg || "cli"} />}
        {tab === "lab" && <Lab cfg={cfg} />}
        {tab === "credentials" && <Credentials />}
        {tab === "learn" && <Learn goToScenarios={goToScenarios} />}
        {tab === "kafka" && <Kafka cfg={cfg} />}
        {tab === "prometheus" && <Prometheus cfg={cfg} />}
      </main>
    </>
  );
}
