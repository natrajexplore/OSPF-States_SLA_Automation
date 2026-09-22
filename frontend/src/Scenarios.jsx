import { useEffect, useRef, useState } from "react";
import { usePoll, useRun } from "./api.js";
import RunPanel from "./RunPanel.jsx";

export default function Scenarios({ focus }) {
  const { data, error } = usePoll("/api/scenarios", 60000);
  const r = useRun();
  const [active, setActive] = useState(null);
  const refs = useRef({});

  useEffect(() => {
    if (focus && refs.current[focus]) {
      refs.current[focus].scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [focus, data]);

  const go = (id, mode) => {
    setActive(`${id} · ${mode}`);
    r.start(`/api/scenarios/${id}/${mode === "apply" ? "run" : "rollback"}`);
  };

  return (
    <>
      {error && <div className="alert bad">Backend: {error}</div>}
      <p className="muted small">
        Apply pushes the configuration to the routers and verifies the result; Rollback undoes it. Runs are serialized. Some scenarios
        wait up to ~90 s for OSPF timers to expire.
      </p>
      <div className="grid one">
        {(data || []).map((s) => (
          <section className={`card${s.id === focus ? " focus" : ""}`} key={s.id} ref={(el) => (refs.current[s.id] = el)}>
            <h3>
              {s.title} <span className="chip">{s.concept}</span>
              <span className="spacer" />
              <button disabled={r.busy} onClick={() => go(s.id, "apply")}>Apply</button>
              <button className="secondary" disabled={r.busy} onClick={() => go(s.id, "rollback")}>Rollback</button>
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
        ))}
      </div>
      {active && <RunPanel title={active} {...r} />}
    </>
  );
}
