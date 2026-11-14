import { useEffect, useState } from "react";
import { usePoll } from "./api.js";
import Monitor from "./Monitor.jsx";
import Scenarios from "./Scenarios.jsx";
import Cli from "./Cli.jsx";
import Lab from "./Lab.jsx";
import Credentials from "./Credentials.jsx";
import Learn from "./Learn.jsx";
import Kafka from "./Kafka.jsx";
import Prometheus from "./Prometheus.jsx";

const TABS = [
  ["lab", "Lab"],
  ["monitor", "Monitor"],
  ["scenarios", "Scenarios"],
  ["cli", "CLI"],
  ["learn", "Learn"],
  ["credentials", "Credentials"],
  ["kafka", "Kafka"],
  ["prometheus", "Prometheus"],
];

// #tab or #tab/arg (for example #cli/R3); #live is the old name of the Lab tab. The Lab tab is the default, as Live labs is in
// the sibling BGP dashboard: it is where scenarios run.
const parseHash = () => {
  const [raw, arg] = location.hash.slice(1).split("/");
  const t = raw === "live" ? "lab" : raw;
  return { tab: TABS.some(([id]) => id === t) ? t : "lab", arg: arg || null };
};

const readTheme = () => {
  try { return localStorage.getItem("ospf-theme") || "dark"; } catch { return "dark"; }
};

function Logo() {
  // three routers on a ring: the OSPF area
  return (
    <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
      <circle cx="13" cy="13" r="11" fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeDasharray="3 2" />
      <circle cx="13" cy="4" r="3" fill="var(--ok)" /><circle cx="5" cy="18" r="3" fill="var(--accent)" />
      <circle cx="21" cy="18" r="3" fill="var(--warn)" />
    </svg>
  );
}

export default function App() {
  const [route, setRoute] = useState(parseHash);
  const [scenarioFocus, setScenarioFocus] = useState(null);
  const [theme, setTheme] = useState(readTheme);
  const { data: cfg, error: cfgErr } = usePoll("/api/config", 15000);
  useEffect(() => {
    const on = () => setRoute(parseHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("ospf-theme", theme); } catch { /* private mode: theme just isn't remembered */ }
  }, [theme]);
  const go = (t, arg) => {
    location.hash = arg ? `${t}/${arg}` : t;
    setRoute({ tab: t, arg: arg || null });
  };
  const goToScenarios = (sid) => {
    setScenarioFocus(sid);
    go("scenarios");
  };
  const { tab, arg } = route;
  const sim = !!cfg?.simulate;
  const ext = (url, label) => url && (
    <a className="btn secondary small" href={url} target="_blank" rel="noreferrer">{label} ↗</a>
  );
  return (
    <>
      <header>
        <div className="brand">
          <Logo />
          <h1>OSPF SLA &amp; States Executor<small>Cisco IOS · EVE-NG · Kafka → Prometheus → Grafana</small></h1>
        </div>
        <nav>
          {TABS.map(([id, label]) => (
            <button key={id} className={tab === id ? "on" : ""} onClick={() => go(id)}>{label}</button>
          ))}
        </nav>
        <span className={`pill ${cfgErr ? "bad" : cfg ? "ok" : "warn"}`}><i />{cfgErr ? "backend down" : cfg ? "connected" : "connecting"}</span>
        {cfg && (sim
          ? <span className="pill sim" title="Routers are modelled in the backend (OSPF_SIMULATE=true); no EVE-NG needed"><i />simulation</span>
          : <span className="pill" title="Real Cisco IOS routers on EVE-NG over SSH"><i style={{ background: "var(--accent)" }} />EVE-NG live</span>)}
        <span className="spacer" />
        {ext(cfg?.grafana_url, "Grafana")}
        {ext(cfg?.prometheus_url, "Prometheus")}
        {ext(cfg?.kafka_ui_url, "Kafka UI")}
        <button className="secondary small" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} title="Light or dark page">
          {theme === "dark" ? "Light" : "Dark"}
        </button>
      </header>
      <main>
        {tab === "monitor" && <Monitor />}
        {tab === "scenarios" && <Scenarios focus={scenarioFocus} />}
        {tab === "cli" && <Cli router={arg} key={arg || "cli"} sim={sim} />}
        {tab === "lab" && <Lab cfg={cfg} goToCli={(r) => go("cli", r)} />}
        {tab === "credentials" && <Credentials sim={sim} />}
        {tab === "learn" && <Learn goToScenarios={goToScenarios} />}
        {tab === "kafka" && <Kafka cfg={cfg} />}
        {tab === "prometheus" && <Prometheus cfg={cfg} />}
      </main>
      <footer>
        <span>{cfg ? `${sim ? "Simulation" : "EVE-NG"} · ${cfg.kafka_enabled ? "Kafka on" : "Kafka off"} · monitor every ${cfg.poll_interval}s` : ""}</span>
        <span className="spacer" />
        <a href="https://github.com/natrajexplore/OSPF-States_SLA_Automation" target="_blank" rel="noreferrer">Source on GitHub</a>
        <span>MIT License</span>
      </footer>
    </>
  );
}
