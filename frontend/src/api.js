import { useCallback, useEffect, useRef, useState } from "react";

export async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let detail = "";
    try {
      detail = (await r.json()).detail || "";
    } catch {
      // body wasn't JSON (or was empty) - fall back to the generic message below
    }
    throw new Error(detail || `${r.status} ${path}${r.status === 502 ? " (backend unreachable)" : ""}`);
  }
  return r.json();
}

/** Poll a JSON endpoint. Keeps the last good value and reports the last error. */
export function usePoll(path, ms = 5000) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    let alive = true;
    const tick = () =>
      api(path)
        .then((d) => alive && (setData(d), setError(null)))
        .catch((e) => alive && setError(e.message));
    tick();
    const id = setInterval(tick, ms);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [path, ms]);
  return { data, error };
}

/**
 * Start a backend run (scenario apply/rollback or baseline reset) and follow it over SSE.
 * `start(url)` POSTs, then streams log lines; when the run ends, the full run record is fetched.
 */
export function useRun() {
  const [lines, setLines] = useState([]);
  const [run, setRun] = useState(null); // full record once finished
  const [runId, setRunId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const es = useRef(null);

  const close = () => es.current && (es.current.close(), (es.current = null));
  useEffect(() => close, []);

  const start = useCallback(async (url, body) => {
    close();
    setLines([]);
    setRun(null);
    setError(null);
    setBusy(true);
    try {
      const { run_id } = await api(url, {
        method: "POST",
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      setRunId(run_id);
      const src = new EventSource(`/api/stream/${run_id}`);
      es.current = src;
      // The run record is the source of truth: if the stream drops mid-run, keep polling it until it is final.
      let done = false;
      let pending = false;
      const finish = async () => {
        if (done || pending) return;
        pending = true;
        try {
          const rec = await api(`/api/runs/${run_id}`);
          if (rec.state === "running") {
            if (rec.log) setLines(rec.log);
            pending = false;
            setTimeout(finish, 2000);
            return;
          }
          done = true;
          src.close();
          if (rec.log) setLines(rec.log);
          setRun(rec);
        } catch (e) {
          done = true;
          setError(e.message);
        }
        setBusy(false);
      };
      src.addEventListener("log", (e) => setLines((l) => [...l, JSON.parse(e.data)]));
      src.addEventListener("result", () => setTimeout(finish, 300));
      src.addEventListener("end", finish);
      src.onerror = () => {
        src.close(); // do not let EventSource auto-reconnect and replay the log twice
        setTimeout(finish, 300);
      };
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }, []);

  return { start, lines, run, runId, busy, error };
}
