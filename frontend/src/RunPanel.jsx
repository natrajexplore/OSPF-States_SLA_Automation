import { useEffect, useRef } from "react";

/** Live console + verify results + before/after diffs for a run started with useRun(). */
export default function RunPanel({ title, lines, run, busy, error }) {
  const box = useRef(null);
  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [lines]);
  if (!busy && !lines.length && !run && !error) return null;

  const state = busy ? "running" : run?.state || (error ? "error" : "");
  return (
    <section className="card run">
      <h3>
        {title} <span className={`badge ${state === "passed" || state === "done" ? "ok" : state === "running" ? "warn" : "bad"}`}>{state}</span>
        {run?.duration != null && <span className="muted small"> {run.duration}s</span>}
      </h3>
      {error && <div className="alert bad">{error}</div>}
      {run?.error && <div className="alert bad">{run.error}</div>}
      <pre className="console" ref={box}>{lines.join("\n") || (busy ? "waiting for output…" : "")}</pre>

      {run?.results?.length > 0 && (
        <>
          <h4>Verification</h4>
          <table>
            <thead><tr><th></th><th>Device</th><th>Command</th><th>Result</th></tr></thead>
            <tbody>
              {run.results.map((r, i) => (
                <tr key={i}>
                  <td><span className={`badge ${r.passed ? "ok" : "bad"}`}>{r.passed ? "PASS" : "FAIL"}</span></td>
                  <td>{r.device}</td><td><code>{r.command}</code></td><td className="muted">{r.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {run.results.map((r, i) => (
            <details key={i}>
              <summary>{r.device}: {r.command}{r.diff ? " (changed)" : ""}</summary>
              {r.diff && <pre className="diff">{r.diff}</pre>}
              <pre className="out">{r.output}</pre>
            </details>
          ))}
        </>
      )}
    </section>
  );
}
