"""The simulated lab: one model for all routers, shared by the scenario engine, the monitor and the CLI tab.

devices.py routes show / push_config / exec_cmd here when OSPF_SIMULATE=true. Calls come from worker threads
(asyncio.to_thread), so every access holds one lock.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from ..config import BASELINE_DIR, load_inventory, settings
from .iosconfig import ConfigSession, RouterConfig, ifname, parse_config
from .ospf import Model
from .render import Renderer


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
        self.model.compute(time.time())          # boot: the baseline is converged

    @staticmethod
    def _baseline(name: str) -> RouterConfig:
        f = BASELINE_DIR / f"{name}.cfg"
        text = f.read_text(encoding="utf-8") if f.is_file() else f"hostname {name}\n"
        return parse_config(text, name)

    # -- device API ---------------------------------------------------------------------------------------------
    def show(self, router: str, command: str) -> str:
        with self._lock:
            now = time.time()
            snap = self.model.compute(now)
            return Renderer(self.model, snap, now, self.born, self.started).show(router, command)

    def push(self, router: str, lines: list[str], save: bool = True) -> str:
        with self._lock:
            cfg = self.model.configs[router]
            sess = ConfigSession(cfg)
            sess.apply(lines)
            self.model.compute(time.time())      # adjacency timers start now, not at the next poll
            host = cfg.hostname
            out = ["configure terminal", "Enter configuration commands, one per line.  End with CNTL/Z.",
                   *sess.transcript, f"{sess.prompt}end", f"{host}#"]
            if save:
                out += ["write mem", "Building configuration...", "[OK]", f"{host}#"]
            return "\n".join(out)

    def exec_cmd(self, router: str, command: str) -> str:
        with self._lock:
            host = self.model.configs[router].hostname
            c = " ".join(command.split()).lower()
            if c.startswith("clear ip ospf") and "process" in c:
                self.model.clear_process(router)
                self.model.compute(time.time())
                return f"{host}#{command}\nReset ALL OSPF processes? [no]: yes\n{host}#"
            if c.startswith("show "):
                return self.show(router, command)
            return f"{host}#{command}\n{host}#"

    def reset(self, router: str) -> str:
        """Push the baseline file: in the model that restores the router's baseline configuration exactly."""
        with self._lock:
            self.model.configs[router] = self._baseline(router)
            self.model.clear_process(router)
            self.model.compute(time.time())
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
