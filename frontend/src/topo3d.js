// 3D view of the OSPF lab (Three.js). Loaded lazily by Topo3D.jsx so the main bundle stays small.
//
//   const v = create(container, { onSelect(name) {} });
//   v.setGraph(graph)            routers on tiers (area 0 on top, ABRs, area 1 below), links, a hub for the broadcast segment
//   v.setState({ nodes, links }) nodes: {R1: "up"|"down"|"wait"|"idle"}; links: {"R3--R4": {R3: "full"|"partial"|"down"|"idle", R4: ...}}
//   v.highlight(names)           routers a scenario configures (amber)
//   v.pulse(name)  v.beam(name)  a router being configured; an SSH command travelling from the executor to it
//   v.tracePath(names, { onHop, loop })   a packet follows the path, pausing at each router; v.stopTrace()
//   v.setAutoRotate(b)  v.setLabels(b)  v.resetCamera()  v.setTheme("dark"|"light")  v.theme()  v.dispose()
// The theme changes the 3D scene only; preferredTheme()/setPreferredTheme() remember it in this browser.
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

const THEMES = {
  dark: { bg: 0x0b1017, grid: [0x22303d, 0x16212b], body: 0x1f2b38, label: "#e6edf3", sub: "#8b9bb0", stroke: "rgba(11,15,20,.92)",
    area0: 0x4aa3ff, area1: 0x2dd4bf, pkt: 0xfff3c4, exec: 0xa371f7 },
  light: { bg: 0xeef2f7, grid: [0xb7c3d0, 0xdbe3ec], body: 0x5c6d80, label: "#1b2733", sub: "#546578", stroke: "rgba(238,242,247,.95)",
    area0: 0x2563eb, area1: 0x0d9488, pkt: 0xb45309, exec: 0x7c3aed },
};
const STATE = { up: 0x3fb950, full: 0x3fb950, wait: 0xd29922, partial: 0xd29922, down: 0xf85149, idle: 0x5b6b7c };
const HL = 0xfbbf24;
const KEY = "ospf3dTheme";
const TIER_Y = [0, 3.4, 6.8];

export function preferredTheme() {
  try { return localStorage.getItem(KEY) === "light" ? "light" : "dark"; } catch { return "dark"; }
}
export function setPreferredTheme(name) {
  try { localStorage.setItem(KEY, name === "light" ? "light" : "dark"); } catch { /* storage blocked: lasts for this view only */ }
}
export function webglSupported() {
  try {
    const c = document.createElement("canvas");
    return !!(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl")));
  } catch { return false; }
}

function textSprite(lines, th, { size = 40, scale = 3.2, color } = {}) {
  const c = document.createElement("canvas"), g = c.getContext("2d"), w = 384, h = 110;
  c.width = w; c.height = h;
  g.textAlign = "center"; g.textBaseline = "middle"; g.lineWidth = 6; g.strokeStyle = th.stroke;
  g.font = `600 ${size}px system-ui, "Segoe UI", sans-serif`; g.fillStyle = color || th.label;
  const y0 = lines[1] ? h * 0.34 : h / 2;
  g.strokeText(lines[0], w / 2, y0); g.fillText(lines[0], w / 2, y0);
  if (lines[1]) {
    g.font = `500 ${Math.round(size * 0.6)}px system-ui, "Segoe UI", sans-serif`; g.fillStyle = th.sub;
    g.strokeText(lines[1], w / 2, h * 0.76); g.fillText(lines[1], w / 2, h * 0.76);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.minFilter = THREE.LinearFilter;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, depthTest: false }));
  sp.scale.set(scale * (w / 320), scale * (h / 320), 1);
  sp.renderOrder = 10;
  return sp;
}

function tube(a, b, color, radius = 0.07) {
  const curve = new THREE.LineCurve3(a, b);
  return new THREE.Mesh(new THREE.TubeGeometry(curve, 1, radius, 8, false),
    new THREE.MeshStandardMaterial({ color, roughness: 0.6, metalness: 0.1 }));
}

function disposeTree(obj) {
  obj.traverse((o) => {
    o.geometry?.dispose();
    const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : [];
    mats.forEach((m) => { m.map?.dispose(); m.dispose(); });
  });
}

export function create(container, handlers = {}) {
  if (!webglSupported()) return null;
  let themeName = handlers.theme || preferredTheme();
  let TH = THEMES[themeName];

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.domElement.style.cssText = "display:block;width:100%;height:100%;outline:none";
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(46, 1, 0.1, 200);
  const controls = new OrbitControls(camera, renderer.domElement);
  Object.assign(controls, { enableDamping: true, dampingFactor: 0.08, maxPolarAngle: Math.PI * 0.49, minDistance: 5,
    maxDistance: 45, autoRotate: true, autoRotateSpeed: 0.5 });
  controls.addEventListener("start", () => { controls.autoRotate = false; handlers.onRotate?.(false); });
  scene.add(new THREE.AmbientLight(0xffffff, 0.9));
  const sun = new THREE.DirectionalLight(0xffffff, 0.9);
  sun.position.set(6, 14, 8);
  scene.add(sun);

  let world = new THREE.Group();
  scene.add(world);
  const st = { graph: null, nodes: {}, links: {}, hub: {}, labels: true, hl: new Set(), pulses: [], beams: [], trace: null,
    traceArgs: null, stateArgs: null, exec: null };
  const clock = new THREE.Clock();

  function applyTheme() {
    renderer.setClearColor(TH.bg, 1);
    scene.fog = new THREE.Fog(TH.bg, 30, 70);
  }

  function pos(name) {
    return st.nodes[name]?.group.position.clone().add(new THREE.Vector3(0, 0.35, 0));
  }

  function build() {
    scene.remove(world);
    disposeTree(world);
    world = new THREE.Group();
    scene.add(world);
    st.nodes = {}; st.links = {}; st.hub = {};
    const g = st.graph;
    if (!g) return;

    const grid = new THREE.GridHelper(40, 20, TH.grid[0], TH.grid[1]);
    grid.position.y = -1.2;
    world.add(grid);

    // routers, spread along x on their tier
    const tiers = {};
    g.nodes.forEach((n) => (tiers[n.tier] ||= []).push(n));
    Object.entries(tiers).forEach(([tier, list]) => {
      list.forEach((n, i) => {
        const grp = new THREE.Group();
        grp.position.set((i - (list.length - 1) / 2) * 8, TIER_Y[tier] ?? 0, 0);
        const body = new THREE.Mesh(new THREE.CylinderGeometry(0.9, 0.9, 0.55, 32),
          new THREE.MeshStandardMaterial({ color: TH.body, roughness: 0.45, metalness: 0.3, emissive: 0x000000 }));
        const ring = new THREE.Mesh(new THREE.TorusGeometry(1.15, 0.09, 12, 48),
          new THREE.MeshBasicMaterial({ color: STATE.idle }));
        ring.rotation.x = Math.PI / 2;
        ring.position.y = -0.3;
        const label = textSprite([n.name, `${n.router_id} · ${n.role}`], TH);
        label.position.y = 1.35;
        label.visible = st.labels;
        body.userData.name = n.name;
        grp.add(body, ring, label);
        world.add(grp);
        st.nodes[n.name] = { group: grp, body, ring, label, data: n };
      });
    });

    // area volumes: every router that has an interface in the area (ABRs are in both, which is what makes them ABRs)
    [0, 1].forEach((area) => {
      const names = new Set(g.links.filter((l) => l.area === area).flatMap((l) => l.members.map((m) => m.node)));
      if (!names.size) return;
      const box = new THREE.Box3();
      names.forEach((n) => box.expandByPoint(st.nodes[n].group.position));
      box.expandByVector(new THREE.Vector3(2, 1.2, 2.4));
      const size = box.getSize(new THREE.Vector3()), c = box.getCenter(new THREE.Vector3());
      const color = area === 0 ? TH.area0 : TH.area1;
      const geo = new THREE.BoxGeometry(size.x, size.y, size.z);
      const fill = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.05, depthWrite: false }));
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.45 }));
      fill.position.copy(c); edges.position.copy(c);
      const tag = textSprite([area === 0 ? "AREA 0 (backbone)" : "AREA 1"], TH, { size: 34, color: `#${color.toString(16).padStart(6, "0")}` });
      tag.position.set(box.min.x + 1.6, area === 0 ? box.max.y + 0.2 : box.min.y + 0.1, box.max.z);
      world.add(fill, edges, tag);
    });

    // links: point-to-point tubes; a broadcast segment gets a hub with one spoke per member
    g.links.forEach((l) => {
      const spokes = {};
      if (l.members.length > 2) {
        const c = new THREE.Vector3();
        l.members.forEach((m) => c.add(st.nodes[m.node].group.position));
        c.divideScalar(l.members.length).add(new THREE.Vector3(0, 0.35, 2.6));
        st.hub[l.name] = c;
        const hub = new THREE.Mesh(new THREE.BoxGeometry(1.1, 0.35, 0.7), new THREE.MeshStandardMaterial({ color: TH.body }));
        hub.position.copy(c);
        const tag = textSprite([l.name, `area ${l.area} · broadcast`], TH, { size: 30, scale: 2.6 });
        tag.position.copy(c).add(new THREE.Vector3(0, 0.9, 0));
        tag.userData.isLabel = true;
        world.add(hub, tag);
        l.members.forEach((m) => {
          spokes[m.node] = tube(pos(m.node), c, STATE.idle);
          world.add(spokes[m.node]);
        });
      } else {
        const [a, b] = l.members;
        const t = tube(pos(a.node), pos(b.node), STATE.idle);
        spokes[a.node] = spokes[b.node] = t;
        world.add(t);
        const tag = textSprite([`${a.if} — ${b.if}`, `area ${l.area} · point-to-point`], TH, { size: 28, scale: 2.4 });
        tag.position.copy(pos(a.node).add(pos(b.node)).multiplyScalar(0.5)).add(new THREE.Vector3(0, 0.6, 0));
        tag.userData.isLabel = true;
        world.add(tag);
      }
      st.links[l.name] = { spokes, data: l };
    });

    // the SSH executor (the backend container): configuration beams start here
    const exec = new THREE.Mesh(new THREE.OctahedronGeometry(0.6), new THREE.MeshStandardMaterial({ color: TH.exec, emissive: TH.exec, emissiveIntensity: 0.35 }));
    exec.position.set(-11, 8.5, -2);
    const et = textSprite(["SSH executor", "backend · Netmiko"], TH, { size: 30, scale: 2.6 });
    et.position.copy(exec.position).add(new THREE.Vector3(0, 1.1, 0));
    et.userData.isLabel = true;
    world.add(exec, et);
    st.exec = exec;

    world.traverse((o) => { if (o.userData.isLabel) o.visible = st.labels; });
    if (st.stateArgs) setState(st.stateArgs);
    highlight([...st.hl]);
    if (st.traceArgs) tracePath(...st.traceArgs);
  }

  function setState(s) {
    st.stateArgs = s;
    Object.entries(s.nodes || {}).forEach(([n, v]) => st.nodes[n]?.ring.material.color.setHex(STATE[v] ?? STATE.idle));
    Object.entries(st.links).forEach(([name, l]) => {
      const ls = (s.links || {})[name] || {};
      const order = ["down", "partial", "full", "idle"];
      if (l.data.members.length > 2) {
        l.data.members.forEach((m) => l.spokes[m.node].material.color.setHex(STATE[ls[m.node] || "idle"]));
      } else {  // one tube: the worse of the two ends
        const worst = l.data.members.map((m) => ls[m.node] || "idle").sort((a, b) => order.indexOf(a) - order.indexOf(b))[0];
        l.spokes[l.data.members[0].node].material.color.setHex(STATE[worst]);
      }
    });
  }

  function highlight(names) {
    st.hl = new Set(names || []);
    Object.entries(st.nodes).forEach(([n, o]) => {
      o.body.material.emissive.setHex(st.hl.has(n) ? HL : 0x000000);
      o.body.material.emissiveIntensity = st.hl.has(n) ? 0.55 : 0;
    });
  }

  function pulse(name) {
    const o = st.nodes[name];
    if (!o) return;
    const m = new THREE.Mesh(new THREE.TorusGeometry(1.2, 0.06, 8, 48), new THREE.MeshBasicMaterial({ color: HL, transparent: true }));
    m.rotation.x = Math.PI / 2;
    m.position.copy(o.group.position);
    world.add(m);
    st.pulses.push({ m, t: 0 });
  }

  function beam(name) {
    const to = pos(name);
    if (!to || !st.exec) return;
    const from = st.exec.position.clone();
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([from, to]),
      new THREE.LineBasicMaterial({ color: TH.exec, transparent: true, opacity: 0.8 }));
    const dot = new THREE.Mesh(new THREE.SphereGeometry(0.16, 12, 12), new THREE.MeshBasicMaterial({ color: TH.exec }));
    world.add(line, dot);
    st.beams.push({ line, dot, from, to, t: 0 });
  }

  // the packet follows the path; consecutive routers on a broadcast segment go through its hub
  function tracePath(names, opts = {}) {
    stopTrace();
    st.traceArgs = [names, opts];
    if (!st.graph || !names?.length || names.some((n) => !st.nodes[n])) return;
    const pts = [pos(names[0])], hops = [0];
    for (let i = 1; i < names.length; i++) {
      const l = st.graph.links.find((x) => x.members.length > 2
        && x.members.some((m) => m.node === names[i - 1]) && x.members.some((m) => m.node === names[i]));
      if (l) pts.push(st.hub[l.name].clone());
      pts.push(pos(names[i]));
      hops.push(pts.length - 1);
    }
    const pkt = new THREE.Mesh(new THREE.SphereGeometry(0.26, 16, 16), new THREE.MeshBasicMaterial({ color: TH.pkt }));
    const glow = new THREE.Mesh(new THREE.SphereGeometry(0.5, 16, 16), new THREE.MeshBasicMaterial({ color: TH.pkt, transparent: true, opacity: 0.25 }));
    pkt.add(glow);
    pkt.position.copy(pts[0]);
    world.add(pkt);
    st.trace = { pts, hops, seg: 0, u: 0, wait: 1.3, pkt, opts, announced: -1 };
    announce(0);
  }

  function announce(ptIdx) {
    const tr = st.trace, h = tr.hops.indexOf(ptIdx);
    if (h >= 0 && h !== tr.announced) { tr.announced = h; tr.opts.onHop?.(h); }
  }

  function stopTrace() {
    if (st.trace) { world.remove(st.trace.pkt); disposeTree(st.trace.pkt); }
    st.trace = null;
    st.traceArgs = null;
  }

  function stepTrace(dt) {
    const tr = st.trace;
    if (!tr) return;
    if (tr.wait > 0) { tr.wait -= dt; return; }
    if (tr.seg >= tr.pts.length - 1) {                  // end of the path: loop after a pause
      if (tr.opts.loop === false) return;
      tr.seg = 0; tr.u = 0; tr.announced = -1; tr.pkt.position.copy(tr.pts[0]); tr.wait = 1.3; announce(0);
      return;
    }
    const a = tr.pts[tr.seg], b = tr.pts[tr.seg + 1], len = a.distanceTo(b) || 1;
    tr.u = Math.min(1, tr.u + (dt * 4.2) / len);
    tr.pkt.position.lerpVectors(a, b, tr.u);
    if (tr.u >= 1) {
      tr.seg++; tr.u = 0;
      if (tr.hops.includes(tr.seg)) { tr.wait = 1.6; announce(tr.seg); }
    }
  }

  function resetCamera() {
    camera.position.set(0, 11, 19);
    controls.target.set(0, 3, 0);
    controls.update();
  }

  // click a router (without dragging) to select it
  const ray = new THREE.Raycaster(), mouse = new THREE.Vector2();
  let down = null;
  const onDown = (e) => { down = [e.clientX, e.clientY]; };
  const onUp = (e) => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5) return;
    const r = renderer.domElement.getBoundingClientRect();
    mouse.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(mouse, camera);
    const hit = ray.intersectObjects(Object.values(st.nodes).map((o) => o.body))[0];
    if (hit) handlers.onSelect?.(hit.object.userData.name);
  };
  renderer.domElement.addEventListener("pointerdown", onDown);
  renderer.domElement.addEventListener("pointerup", onUp);

  const resize = () => {
    const w = container.clientWidth || 300, h = container.clientHeight || 300;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  const ro = new ResizeObserver(resize);
  ro.observe(container);

  let raf = 0;
  const loop = () => {
    raf = requestAnimationFrame(loop);
    const dt = Math.min(clock.getDelta(), 0.1);
    controls.update();
    st.pulses = st.pulses.filter((p) => {
      p.t += dt;
      p.m.scale.setScalar(1 + p.t * 1.6);
      p.m.material.opacity = Math.max(0, 1 - p.t / 1.1);
      if (p.t < 1.1) return true;
      world.remove(p.m); disposeTree(p.m); return false;
    });
    st.beams = st.beams.filter((b) => {
      b.t += dt;
      b.dot.position.lerpVectors(b.from, b.to, Math.min(1, b.t / 0.7));
      b.line.material.opacity = Math.max(0, 0.8 - b.t / 1.2);
      if (b.t < 1.0) return true;
      world.remove(b.line, b.dot); disposeTree(b.line); disposeTree(b.dot); return false;
    });
    stepTrace(dt);
    renderer.render(scene, camera);
  };

  applyTheme();
  resize();
  resetCamera();
  loop();

  return {
    setGraph(g) { st.graph = g; build(); },
    setState, highlight, pulse, beam, tracePath, stopTrace, resetCamera,
    setAutoRotate(on) { controls.autoRotate = on; },
    setLabels(on) {
      st.labels = on;
      world.traverse((o) => { if (o.userData.isLabel) o.visible = on; });
      Object.values(st.nodes).forEach((o) => { o.label.visible = on; });
    },
    theme: () => themeName,
    setTheme(name) { themeName = name === "light" ? "light" : "dark"; TH = THEMES[themeName]; applyTheme(); build(); },
    dispose() {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      controls.dispose();
      disposeTree(scene);
      renderer.dispose();
      renderer.domElement.remove();
    },
  };
}
