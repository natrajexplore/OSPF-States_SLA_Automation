import { useEffect, useRef, useState } from "react";
import { usePoll, useRun } from "./api.js";
import RunPanel from "./RunPanel.jsx";

/** Each card owns its own run state, so scenarios targeting different routers can apply/rollback
 * at the same time - the backend only blocks two runs that actually share a target router. */
function ScenarioCard({ s, focused, cardRef }) {
  const r = useRun();
  const [mode, setMode] = useState(null);

  const go = (m) => {
    setMode(m);
    r.start(`/api/scenarios/${s.id}/${m === "apply" ? "run" : "rollback"}`);
  };

  return (
    <>
      <section className={`card${focused ? " focus" : ""}`} ref={cardRef}>
        <h3>
          {s.title} <span className="chip">{s.concept}</span>
          <span className="spacer" />
          <button disabled={r.busy} onClick={() => go("apply")}>Apply</button>
          <button className="secondary" disabled={r.busy} onClick={() => go("rollback")}>Rollback</button>
        </h3>
        <p>{s.summary}</p>
        <p className="muted small">
          Targets: {s.targets.join(", ")} · settle {s.settle_seconds ?? 10}s
          {s.post_commands?.length ? ` · then: ${s.post_commands.join("; ")}` : ""}
        </p>
        <details>
          <summary>Verify assertions</summary>
          <ul className="small">
            {(s.verify || []).map((v, i) => (
              <li key={i}>
                {v.device}: <code>{v.command}</code> {v.expect_regex ? <>must match <code>{v.expect_regex}</code></> : <>must not match <code>{v.must_not_match}</code></>}
              </li>
            ))}
          </ul>
        </details>
      </section>
      {mode && <RunPanel title={`${s.id} · ${mode}`} {...r} />}
    </>
  );
}

export default function Scenarios({ focus }) {
  const { data, error } = usePoll("/api/scenarios", 60000);
  const refs = useRef({});

  useEffect(() => {
    if (focus && refs.current[focus]) {
      refs.current[focus].scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [focus, data]);

  return (
    <>
      {error && <div className="alert bad">Backend: {error}</div>}
      <p className="muted small">
        Apply pushes the configuration to the routers and verifies the result; Rollback undoes it. Scenarios that
        target different routers can run at the same time - two that share a router are blocked (with a clear
        "already running on: ..." error) until the first one finishes. Some scenarios wait up to ~90 s for OSPF
        timers to expire.
      </p>
      <div className="grid one">
        {(data || []).map((s) => (
          <ScenarioCard key={s.id} s={s} focused={s.id === focus} cardRef={(el) => (refs.current[s.id] = el)} />
        ))}
      </div>
    </>
  );
}
