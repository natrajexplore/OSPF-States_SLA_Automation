"""Every scenario, apply then rollback, against the simulated lab: the scenario's own verify / rollback_verify
assertions must pass, and the baseline must be healthy before and after."""
import pytest

from app import scenarios, validate
from app.sim.driver import lab

SCENARIOS = [s["id"] for s in scenarios.list_scenarios()]


def _run(sc: dict, rollback: bool) -> list[dict]:
    L = lab()
    for t in sc["targets"]:
        L.push(t, scenarios.render(sc, rollback, t))
    for cmd in sc.get("post_commands", []):
        for t in sc["targets"]:
            L.exec_cmd(t, cmd)
    verify = scenarios.verify_for(sc, rollback)
    captured = {f"{v['device']} :: {v['command']}": L.show(v["device"], v["command"]) for v in verify}
    return validate.evaluate(verify, captured)


def _baseline_healthy() -> None:
    L = lab()
    for r, peers in {"R1": ["10.255.0.2", "10.255.0.3"], "R2": ["10.255.0.1", "10.255.0.3", "10.255.0.4"],
                     "R3": ["10.255.0.1", "10.255.0.2", "10.255.0.4"], "R4": ["10.255.0.2", "10.255.0.3"]}.items():
        out = L.show(r, "show ip ospf neighbor")
        for p in peers:
            assert validate.assert_regex(rf"{p.replace('.', chr(92) + '.')}\s+\d+\s+(FULL|2WAY)", out), f"{r} -> {p}\n{out}"


def test_catalogue_complete():
    assert len(SCENARIOS) == 18


# scenarios whose apply assertions already hold on the baseline, by design: 13 shows that a missing `subnets` keyword
# redistributes nothing, so "172.16.199.0 is absent" is true before and after
_HOLDS_ON_BASELINE = {"13_subnets_keyword"}


def _prepare(sc: dict) -> None:
    lab().reset_all()
    _baseline_healthy()
    for pre in sc.get("requires", []):
        for r in _run(scenarios.get_scenario(pre), rollback=False):
            assert r["passed"], f"prerequisite {pre}: {r['reason']}"


@pytest.mark.parametrize("sid", SCENARIOS)
def test_assertions_fail_before_apply(sid):
    """Proves the model reacts: on the untouched lab at least one apply assertion must fail."""
    sc = scenarios.get_scenario(sid)
    _prepare(sc)
    L = lab()
    verify = scenarios.verify_for(sc, False)
    captured = {f"{v['device']} :: {v['command']}": L.show(v["device"], v["command"]) for v in verify}
    results = validate.evaluate(verify, captured)
    if sid in _HOLDS_ON_BASELINE:
        assert all(r["passed"] for r in results)
    else:
        assert not all(r["passed"] for r in results), f"{sid}: apply assertions already pass on the baseline"


@pytest.mark.parametrize("sid", SCENARIOS)
def test_apply_then_rollback(sid):
    sc = scenarios.get_scenario(sid)
    _prepare(sc)
    for r in _run(sc, rollback=False):
        assert r["passed"], f"{sid} apply: {r['device']} {r['command']}: {r['reason']}\n{r['output']}"
    for r in _run(sc, rollback=True):
        assert r["passed"], f"{sid} rollback: {r['device']} {r['command']}: {r['reason']}\n{r['output']}"
