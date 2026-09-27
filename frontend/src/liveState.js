// Turn the monitor snapshot (/api/monitor/state) and EVE-NG node status (/api/devices) into the colours of the 3D view.
//   node: up (answers), down (monitor cannot reach it), idle (no data yet, or the EVE node is stopped)
//   link end: full, partial (neighbor seen but not FULL), down (neighbor missing or DOWN), idle (no data)
// On the broadcast segment two DROTHERs stay in 2WAY by design, so 2WAY counts as healthy there.
// af "v4" colours links by OSPFv2 adjacencies, "v6" by OSPFv3 (monitor field neighbors_v6, filled once scenario 17 runs).
export function liveState(graph, monitor, devices, af = "v4") {
  const field = af === "v6" ? "neighbors_v6" : "neighbors";
  if (!graph) return null;
  const mon = Object.fromEntries((monitor || []).map((r) => [r.router, r]));
  const eve = Object.fromEntries((devices || []).map((d) => [d.name, d.status]));
  const rid = Object.fromEntries(graph.nodes.map((n) => [n.name, n.router_id]));
  const nodes = {};
  graph.nodes.forEach((n) => {
    const m = mon[n.name];
    nodes[n.name] = eve[n.name] === "stopped" || !m ? "idle" : m.reachable ? "up" : "down";
  });
  const links = {};
  graph.links.forEach((l) => {
    const broadcast = l.members.length > 2;
    links[l.name] = {};
    l.members.forEach((me) => {
      const m = mon[me.node];
      if (!m || nodes[me.node] !== "up") return (links[l.name][me.node] = "idle");
      const states = l.members.filter((p) => p.node !== me.node).map((p) => {
        const nb = (m[field] || []).find((x) => x.neighbor === rid[p.node]);
        if (!nb || nb.state === "DOWN") return "down";
        return nb.full || (broadcast && nb.state === "2WAY") ? "full" : "partial";
      });
      links[l.name][me.node] = states.includes("down") ? (states.every((s) => s === "down") ? "down" : "partial")
        : states.includes("partial") ? "partial" : "full";
    });
  });
  return { nodes, links };
}

// The PuTTY link that scripts/putty-setup.ps1 registers: opens the saved session "OSPF <lab> <router>".
export const puttyHref = (lab, router) => `ospfputty:${lab}/${router}`;
