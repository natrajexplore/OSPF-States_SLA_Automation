import { useEffect, useRef, useState } from "react";

// React wrapper for topo3d.js (loaded on first use, so Three.js is its own chunk).
//   graph      GET /api/graph                 state      {nodes, links} for live colours (see topo3d.js)
//   highlight  routers to mark amber          trace      {path: [...], onHop(i)} an animated packet, or null
//   onSelect   click on a router              onReady    receives the engine (pulse/beam from the Lab tab)
export default function Topo3D({ graph, state, highlight, trace, onSelect, onReady, height = 460 }) {
  const host = useRef(null);
  const [v, setV] = useState(null);
  const [err, setErr] = useState(null);
  const [ui, setUi] = useState({ rot: true, names: true, play: true, theme: "dark" });
  const cb = useRef({});
  cb.current = { onSelect, onHop: trace?.onHop };

  useEffect(() => {
    let alive = true, eng = null;
    import("./topo3d.js")
      .then((m) => {
        if (!alive || !host.current) return;
        eng = m.create(host.current, {
          onSelect: (n) => cb.current.onSelect?.(n),
          onRotate: (on) => setUi((u) => ({ ...u, rot: on })),
        });
        if (!eng) return setErr("The 3D view needs WebGL, which this browser does not offer.");
        eng._setPreferredTheme = m.setPreferredTheme;
        setUi((u) => ({ ...u, theme: eng.theme() }));
        setV(eng);
        onReady?.(eng);
      })
      .catch((e) => alive && setErr(`The 3D view could not load (${e.message}).`));
    return () => { alive = false; eng?.dispose(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { if (v && graph) v.setGraph(graph); }, [v, graph]);
  useEffect(() => { if (v && state) v.setState(state); }, [v, state]);
  useEffect(() => { if (v) v.highlight(highlight || []); }, [v, highlight, graph]);
  const pathKey = trace ? `${trace.key || ""}|${trace.path.join(">")}` : "";
  useEffect(() => {
    if (!v || !graph) return;
    if (pathKey && ui.play) v.tracePath(trace.path, { onHop: (i) => cb.current.onHop?.(i) });
    else v.stopTrace();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [v, graph, pathKey, ui.play]);

  const tool = (key, fn) => () => { setUi((u) => ({ ...u, [key]: !u[key] })); fn?.(!ui[key]); };
  const flipTheme = () => {
    const next = ui.theme === "light" ? "dark" : "light";
    v._setPreferredTheme(next);
    v.setTheme(next);
    setUi((u) => ({ ...u, theme: next }));
  };

  return (
    <div className={`t3d ${ui.theme}`}>
      <div className="t3d-bar">
        {trace && <button className={ui.play ? "on" : ""} onClick={tool("play")}>{ui.play ? "Pause" : "Play"}</button>}
        <button className={ui.rot ? "on" : ""} onClick={tool("rot", (on) => v?.setAutoRotate(on))}>Rotate</button>
        <button className={ui.names ? "on" : ""} onClick={tool("names", (on) => v?.setLabels(on))}>Names</button>
        <button onClick={flipTheme} disabled={!v} title="Light or dark 3D scene (the page is unchanged)">{ui.theme === "light" ? "Dark" : "Light"}</button>
        <button onClick={() => v?.resetCamera()} disabled={!v}>Reset view</button>
      </div>
      <div className="t3d-canvas" ref={host} style={{ height }}>
        {err && <div className="t3d-none">{err}</div>}
      </div>
    </div>
  );
}
