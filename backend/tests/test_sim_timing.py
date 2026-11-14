"""Simulation timing: a new adjacency forms over OSPF_SIM_CONVERGE seconds, starting when the change is pushed (not at the
next monitor poll), and a scenario's settle time always covers it."""
import pytest

from app import scenarios, validate
from app.config import settings
from app.sim import driver


class Clock:
    def __init__(self, t: float) -> None:
        self.t = t

    def time(self) -> float:
        return self.t


@pytest.fixture
def clock(monkeypatch):
    c = Clock(1_000_000.0)
    monkeypatch.setattr(driver, "time", c)
    monkeypatch.setattr(settings, "sim_converge", 4.0)
    lab = driver.lab()
    lab.reset_all()
    lab.model.converge = 4.0
    yield c
    lab.model.converge = 0.0


def _push(sc, rollback):
    lab = driver.lab()
    for t in sc["targets"]:
        lab.push(t, scenarios.render(sc, rollback, t))
    for cmd in sc.get("post_commands", []):
        for t in sc["targets"]:
            lab.exec_cmd(t, cmd)


@pytest.mark.parametrize("sid", ["09_mtu_mismatch", "01_adjacency", "02_dr_bdr", "11_area_mismatch"])
def test_rollback_converges_within_settle(clock, sid):
    sc = scenarios.get_scenario(sid)
    _push(sc, rollback=False)
    clock.t += 60
    _push(sc, rollback=True)
    lab = driver.lab()
    full = r"10\.255\.0\.4\s+\d+\s+FULL" if sid != "02_dr_bdr" else r"10\.255\.0\.1\s+\d+\s+FULL"
    clock.t += 1.0                                   # still forming one second after the change
    assert not validate.assert_regex(full, lab.show("R3", "show ip ospf neighbor"))
    clock.t += scenarios.settle_time(sc.get("settle_seconds", 10)) - 1.0
    verify = scenarios.verify_for(sc, rollback=True)
    captured = {f"{v['device']} :: {v['command']}": lab.show(v["device"], v["command"]) for v in verify}
    for r in validate.evaluate(verify, captured):
        assert r["passed"], f"{sid}: {r['reason']}\n{r['output']}"
