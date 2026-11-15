"""The simulated lab: one model for all routers, shared by the scenario engine, the monitor, the CLI tab and the SSH
logins (sshd.py).

devices.py routes show / push_config / exec_cmd here when OSPF_SIMULATE=true. Calls come from worker threads
(asyncio.to_thread), so every access holds one lock.

Besides the OSPF model the lab keeps what a real router would: every port of the chassis (unused ones shut down),
a syslog buffer per router (%OSPF-5-ADJCHG when an adjacency comes up or goes down, %SYS-5-CONFIG_I after a
configuration change), the startup-config saved by `write memory`, and the SSH users logged in.
"""
from __future__ import annotations

import collections
import threading
import time
from time import gmtime, strftime          # not time.*: the timing tests replace `time` with a fake clock
from pathlib import Path

from ..config import BASELINE_DIR, load_inventory, settings
from .iosconfig import ConfigSession, RouterConfig, ifname, parse_config
from .iosshow import HARDWARE, render_running_config
from .ospf import Model
from .render import Renderer

AUTOMATION_ADDR = "192.168.99.1"          # where the dashboard's SSH sessions come from, as the routers see it


def stamp(t: float) -> str:
    """IOS `service timestamps log datetime msec` (the * means the clock is not NTP-synchronised)."""
    return strftime("*%b %d %H:%M:%S", gmtime(t)) + f".{int(t * 1000) % 1000:03d}"


class SimLab:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.started = time.time()
        self.born: dict = {}
        self._load()

    def _load(self) -> None:
        inv = load_inventory()
        self.names = list(inv["devices"])
        configs: dict[str, RouterConfig] = {name: self._baseline(name) for name in self.names}
        links = [{"name": ln["name"], "members": [(m["node"], ifname(m["if"])) for m in ln["members"]]}
                 for ln in inv.get("links", [])]
        self.model = Model(configs, links, converge=settings.sim_converge)
        self.logs: dict[str, collections.deque] = {n: collections.deque(maxlen=400) for n in self.names}
        self.log_seq = 0                                  # grows with every message (terminal monitor follows it)
        self.feed: collections.deque = collections.deque(maxlen=2000)   # (seq, router, line)
        self.changed: dict[str, float] = {}
        self.changed_by: dict[str, str] = {}
        self.sessions: dict[str, list] = collections.defaultdict(list)  # router -> [(user, line, peer, since)]
        self._nbr: dict | None = None
        self._compute(time.time())                       # boot: the baseline is converged, nothing to log
        self.startup = {n: render_running_config(c) for n, c in configs.items()}
        for n in self.names:
            self.log(n, "%SYS-5-RESTART: System restarted --", self.started)
            self.log(n, "%SYS-6-LOGGINGHOST_STARTSTOP: Logging to host 127.0.0.1 port 514 started - CLI initiated",
                     self.started)

    @staticmethod
    def _baseline(name: str) -> RouterConfig:
        f = BASELINE_DIR / f"{name}.cfg"
        text = f.read_text(encoding="utf-8") if f.is_file() else f"hostname {name}\n"
        cfg = parse_config(text, name)
        for port in HARDWARE:                             # the chassis' other ports exist too, shut down
            if port not in cfg.ifaces:
                cfg.iface(port).shutdown = True
        return cfg

    # -- syslog -----------------------------------------------------------------------------------------------------
    def log(self, router: str, msg: str, t: float | None = None) -> None:
        line = f"{stamp(t or time.time())}: {msg}"
        self.logs[router].append(line)
        self.log_seq += 1
        self.feed.append((self.log_seq, router, line))

    def since(self, router: str, seq: int) -> tuple[int, list[str]]:
        """Messages for `router` after `seq` (terminal monitor), and the newest seq."""
        with self._lock:
            self._compute(time.time())
            return self.log_seq, [ln for s, r, ln in self.feed if s > seq and r == router]

    def _compute(self, now: float):
        """Run the model and log every adjacency that reached or left FULL since the last run."""
        snap = self.model.compute(now)
        cur = {}
        for af, view in (("v4", snap.v4), ("v6", snap.v6)):
            for r, nbrs in view.neighbors.items():
                for n in nbrs:
                    cur[(af, r, n.rid, n.iface)] = n.state
        if self._nbr is not None:
            for key in set(cur) | set(self._nbr):
                af, r, rid, ifn = key
                old, new = self._nbr.get(key), cur.get(key)
                tag = "%OSPF-5-ADJCHG: Process 1" if af == "v4" else "%OSPFv3-5-ADJCHG: Process 1, IPv6"
                if new == "FULL" and old != "FULL":
                    self.log(r, f"{tag}, Nbr {rid} on {ifn} from LOADING to FULL, Loading Done", now)
                elif old == "FULL" and new != "FULL":
                    i = self.model.configs[r].ifaces.get(ifn)
                    why = "Interface down or detached" if (i is None or i.shutdown) else "Dead timer expired"
                    self.log(r, f"{tag}, Nbr {rid} on {ifn} from FULL to DOWN, Neighbor Down: {why}", now)
        self._nbr = cur
        return snap

    def _configured(self, router: str, user: str, line: str, peer: str) -> None:
        now = time.time()
        self.changed[router] = now
        self.changed_by[router] = user
        self.log(router, f"%SYS-5-CONFIG_I: Configured from console by {user} on {line} ({peer})", now)

    # -- device API ---------------------------------------------------------------------------------------------
    def renderer(self, now: float) -> Renderer:
        snap = self._compute(now)
        rd = Renderer(self.model, snap, now, self.born, self.started)
        rd.lab = self
        return rd

    def show(self, router: str, command: str) -> str:
        """A `show` as the router answers it. Abbreviations (`sh ip int br`) and output filters (`| include ...`) work
        as on IOS, through the SSH shell's command parser."""
        from .render import INVALID
        with self._lock:
            rd = self.renderer(time.time())
            out = rd.show(router, command)
            if out != INVALID:
                return out
            from .sshd import ParseError, _pipe, parse     # lazy: sshd imports this module
            body, bar, pipe = command.partition("|")
            try:
                full = " ".join(parse(body))
            except ParseError:
                return out
            out = rd.show(router, full)
            return _pipe(out, pipe) if bar and out != INVALID else out

    def snapshot(self):
        with self._lock:
            return self._compute(time.time())

    def push(self, router: str, lines: list[str], save: bool = True) -> str:
        with self._lock:
            cfg = self.model.configs[router]
            sess = ConfigSession(cfg)
            sess.apply(lines)
            self._compute(time.time())               # adjacency timers start now, not at the next poll
            self._configured(router, settings.device_user, "vty0", AUTOMATION_ADDR)
            host = cfg.hostname
            out = ["configure terminal", "Enter configuration commands, one per line.  End with CNTL/Z.",
                   *sess.transcript, f"{sess.prompt}end", f"{host}#"]
            if save:
                self.write_mem(router)
                out += ["write mem", "Building configuration...", "[OK]", f"{host}#"]
            return "\n".join(out)

    def config_line(self, router: str, mode: tuple, line: str) -> tuple:
        """One line typed in configuration mode (the SSH shell). Takes and returns the session's mode, so a session
        keeps working when Rollback / reset replaces the router's configuration object underneath it."""
        with self._lock:
            sess = ConfigSession(self.model.configs[router])
            sess.mode = mode
            sess.apply([line])
            self._compute(time.time())
            self.changed[router] = time.time()
            return sess.mode

    def config_done(self, router: str, user: str, line: str, peer: str) -> None:
        """An SSH user left configuration mode (end / Ctrl-Z): IOS logs %SYS-5-CONFIG_I."""
        with self._lock:
            self._configured(router, user, line, peer)

    def write_mem(self, router: str) -> None:
        with self._lock:
            self.startup[router] = render_running_config(self.model.configs[router])

    def exec_cmd(self, router: str, command: str) -> str:
        with self._lock:
            host = self.model.configs[router].hostname
            c = " ".join(command.split()).lower()
            if c.startswith("clear ip ospf") and "process" in c:
                self.model.clear_process(router)
                self._compute(time.time())
                return f"{host}#{command}\nReset ALL OSPF processes? [no]: yes\n{host}#"
            if c.startswith("show "):
                return self.show(router, command)
            return f"{host}#{command}\n{host}#"

    def reset(self, router: str) -> str:
        """Push the baseline file: in the model that restores the router's baseline configuration exactly."""
        with self._lock:
            self.model.configs[router] = self._baseline(router)
            self.model.clear_process(router)
            self._compute(time.time())
            self._configured(router, settings.device_user, "vty0", AUTOMATION_ADDR)
            self.write_mem(router)
            lines = (BASELINE_DIR / f"{router}.cfg").read_text(encoding="utf-8").splitlines() \
                if (BASELINE_DIR / f"{router}.cfg").is_file() else []
            n = sum(1 for ln in lines if ln.strip() and not ln.strip().startswith("!"))
            return (f"configure terminal\nEnter configuration commands, one per line.  End with CNTL/Z.\n"
                    f"! {n} baseline lines applied\n{router}(config)#end\n{router}#\nwrite mem\nBuilding configuration...\n[OK]\n{router}#")

    def reset_all(self) -> None:
        with self._lock:
            self.born.clear()
            self.started = time.time()
            self._load()


_LAB: SimLab | None = None
_LAB_LOCK = threading.Lock()


def lab() -> SimLab:
    global _LAB
    with _LAB_LOCK:
        if _LAB is None:
            _LAB = SimLab()
        return _LAB


def is_baseline(router: str, path: str) -> bool:
    try:
        return Path(path).resolve() == (BASELINE_DIR / f"{router}.cfg").resolve()
    except OSError:
        return False


class SimEveClient:
    """Stands in for the EVE-NG REST client: every router of the inventory is running, no console ports."""

    def enrich(self) -> dict:
        return {name.upper(): {"id": str(k + 1), "status": "running", "console_host": None, "console_port": None}
                for k, name in enumerate(load_inventory()["devices"])}

    def nodes(self) -> dict:
        return {str(k + 1): {"name": name, "status": 2, "url": ""} for k, name in enumerate(load_inventory()["devices"])}

    def topology(self) -> list:
        out = []
        for ln in load_inventory().get("links", []):
            ms = ln["members"]
            for a in ms[1:]:
                out.append({"source": ms[0]["node"], "destination": a["node"]})
        return out
