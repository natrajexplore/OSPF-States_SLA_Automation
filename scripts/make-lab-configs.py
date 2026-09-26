"""Write labs/<lab>/CONFIGS.md for every lab: the links, every router's full baseline configuration, and the scenario
commands (apply and rollback, rendered from the Jinja templates per target router) with the checks, so a lab can be
built by hand on the consoles.

    python scripts/make-lab-configs.py            # all labs
    python scripts/make-lab-configs.py 06_nssa
The baseline .cfg files, inventory.yaml and scenarios/templates are the source of truth; CONFIGS.md is generated from them."""
import pathlib
import sys

import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = pathlib.Path(__file__).resolve().parent.parent
LABS = ROOT / "labs"


def checks(title: str, items: list[dict], settle: int) -> list[str]:
    if not items:
        return []
    out = [f"**{title}** (after about {settle} s):", ""]
    for c in items:
        if "expect_regex" in c:
            out.append(f"- `{c['device']}# {c['command']}` must match `{c['expect_regex']}`")
        else:
            out.append(f"- `{c['device']}# {c['command']}` must **not** match `{c['must_not_match']}`")
    return out + [""]


def scenario_block(lab: pathlib.Path, inv: dict, sc_file: pathlib.Path) -> str:
    sc = yaml.safe_load(sc_file.read_text(encoding="utf-8"))
    env = Environment(loader=FileSystemLoader(str(lab / "templates")), keep_trailing_newline=True)
    variables = {**inv.get("globals", {}), **sc.get("vars", {})}

    def render(rollback: bool, target: str) -> str:
        text = env.get_template(sc["template"]).render(**variables, rollback=rollback, target=target)
        return "\n".join(ln.rstrip() for ln in text.splitlines() if ln.strip())

    def per_target(rollback: bool) -> list[str]:
        blocks = {t: render(rollback, t) for t in sc["targets"]}
        if len(set(blocks.values())) == 1:           # same lines on every target: show them once
            return ["```", next(iter(blocks.values())), "```", ""]
        out = []
        for t, text in blocks.items():
            out += [f"On **{t}**:", "", "```", text, "```", ""]
        return out

    settle = sc.get("settle_seconds", 8)
    out = [f"### Scenario `{sc_file.stem}`: {sc['title']}", "", " ".join(sc.get("summary", "").split()), "",
           f"Push to: **{', '.join(sc['targets'])}**, in configuration mode.", "", "**Apply**", ""]
    out += per_target(False)
    if sc.get("post_commands"):
        out += ["Then, in exec mode on each target (answer `yes`):", "", "```", *sc["post_commands"], "```", ""]
    out += checks("Check the result", sc.get("verify", []), settle)
    out += ["**Roll back**", ""] + per_target(True)
    if sc.get("post_commands"):
        out += ["Then again, in exec mode on each target:", "", "```", *sc["post_commands"], "```", ""]
    out += checks("Check the rollback", sc.get("rollback_verify", []), settle)
    return "\n".join(out)


def build(lab: pathlib.Path) -> str:
    raw = (lab / "inventory.yaml").read_text(encoding="utf-8")
    inv = yaml.safe_load(raw)
    title = next((ln.split(":", 1)[1].strip() for ln in raw.splitlines() if ln.startswith("# Lab")), lab.name)
    md = [f"# {lab.name}: all device configurations", "",
          title, "",
          "Everything below is generated from `inventory.yaml`, `baseline/*.cfg`, and `scenarios/` + `templates/` of this lab by",
          "`python scripts/make-lab-configs.py`. Do not edit it by hand. The topology, the use case and the expected output are in `README.md`.", "",
          "## How to use it by hand", "",
          f"1. Import and start the lab (`labs/labtool.sh {lab.name} import` and `start`, or import `{lab.name}.zip` in the EVE web UI and start all nodes).",
          "2. Open each router's console. A fresh router asks `Would you like to enter the initial configuration dialog? [yes/no]:`. Answer `no`, press Enter, then type `enable`.",
          "3. Type `configure terminal` and paste that router's block below, then `end` and `write memory`.",
          "4. Routers can be pasted in any order. Adjacencies come up as soon as both ends of a link are configured (about 40 s on the broadcast segment, the OSPF wait timer).", "",
          "**Management lines.** Every block contains a small management section (`ip vrf MGMT`, `FastEthernet0/0` in that VRF, `ip route vrf MGMT`, "
          "`username lab`, `enable secret`, `line vty`). It lets the dashboard and `labtool.sh` log in over SSH and is not part of the OSPF design. "
          "For a hand-built lab you can leave it out and use only the console. To use SSH you also need `crypto key generate rsa modulus 1024` once per "
          "router (`scripts/bootstrap.py` does that).", "",
          "**`no ...` lines in the baselines.** The baselines are also used to *reset* a router, so they contain `no` lines (for example `no area 1 stub`) that "
          "remove whatever a scenario may have left. On a blank router they are harmless.", "",
          "## Links", "", "| Segment | Members | Note |", "|---|---|---|"]
    notes = {}
    for ln in raw.splitlines():
        if ln.strip().startswith("- name:") and "#" in ln:
            notes[ln.split("name:", 1)[1].split("#", 1)[0].strip()] = ln.split("#", 1)[1].strip()
    for link in inv["links"]:
        members = ", ".join(f"{m['node']} {m['if']}" for m in link["members"])
        md.append(f"| {link['name']} | {members} | {notes.get(link['name'], '')} |")
    md += ["", "## Devices", "", "| Router | Role | Router ID | Management IP |", "|---|---|---|---|"]
    for name, d in inv["devices"].items():
        md.append(f"| {name} | {d.get('role', '')} | {d.get('router_id', '')} | {d.get('mgmt_ip', '')} |")
    md.append("")
    for cfg in sorted((lab / "baseline").glob("*.cfg")):
        md += [f"## {cfg.stem}", "", "```", cfg.read_text(encoding="utf-8").rstrip(), "```", ""]
    scenarios = sorted((lab / "scenarios").glob("*.yaml"))
    if scenarios:
        md += ["## Scenarios (the change the lab is about)", ""]
        md += [scenario_block(lab, inv, sc) for sc in scenarios]
    probes = lab / "probes.txt"
    if probes.exists():
        md += ["## Commands used by `labtool.sh capture`", "", "```"]
        md += [f"{d}# {c}" for d, c in (ln.split("|", 1) for ln in probes.read_text(encoding="utf-8").splitlines() if "|" in ln)]
        md += ["```", ""]
    return "\n".join(md)


def main(argv: list[str]) -> int:
    labs = [LABS / a for a in argv] if argv else sorted(p for p in LABS.iterdir() if (p / "baseline").is_dir())
    for lab in labs:
        (lab / "CONFIGS.md").write_text(build(lab), encoding="utf-8", newline="\n")
        print("wrote", lab.relative_to(ROOT) / "CONFIGS.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
