# labs/

## The shared lab

`ospf-sla.unl` is the 4-router lab the dashboard runs all 18 scenarios on. It is generated from
[`backend/inventory.yaml`](../backend/inventory.yaml) by `backend/scripts/build_lab.py`; its configurations are in
[`backend/baseline/`](../backend/baseline/). Topology and addressing: [`docs/lab.md`](../docs/lab.md).

## The standalone topic labs

One folder per OSPF topic, each pairing a **concept** scenario (01-08: the feature working) with the **production failure**
scenario that belongs to it (09-16: the mistake that shows up in incident reports). They are driven with `labtool.sh`, not the
dashboard.

| Lab | Topic | Scenarios | Status |
|---|---|---|---|
| [`01_adjacency/`](01_adjacency/) | Neighbor states; a hello-timer mismatch and an MTU mismatch that stop an adjacency at different states | `01_adjacency`, `09_mtu_mismatch` | Scenarios pass on the shared lab |
| [`02_dr_bdr/`](02_dr_bdr/) | DR/BDR election by priority (non-preemptive), and a network-type mismatch on a point-to-point link | `02_dr_bdr`, `10_network_type_mismatch` | Scenarios pass on the shared lab |
| [`03_inter_area/`](03_inter_area/) | The ABR's type-3 summary (`O IA`), and an area-ID mismatch that silently drops hellos | `03_inter_area`, `11_area_mismatch` | Scenarios pass on the shared lab |
| [`04_stub_area/`](04_stub_area/) | A stub area with an injected default, and a stub flag rolled out to one router only | `04_stub_area`, `12_partial_stub_rollout` | Scenarios pass on the shared lab |
| [`05_external_routes/`](05_external_routes/) | An ASBR and `O E2` routes, and redistribution without `subnets` | `05_external_e2`, `13_subnets_keyword` | Scenarios pass on the shared lab |
| [`06_nssa/`](06_nssa/) | NSSA type-7 to type-5 translation, and a translator takeover with `translate type7 always` | `06_nssa`, `14_dual_nssa_translator` | Scenarios pass on the shared lab |
| [`07_cost_steering/`](07_cost_steering/) | Steering traffic by cost (ECMP to a single path), and a reference-bandwidth mismatch | `07_cost_steering`, `15_reference_bandwidth_mismatch` | Scenarios pass on the shared lab |
| [`08_fast_convergence/`](08_fast_convergence/) | Sub-second failure detection with fast hellos; BFD for reference only | `08_bfd`, `16_fast_hello_no_bfd` | `16` passes; **`08` wedges Dynamips, do not run** |
| [`09_ospfv3/`](09_ospfv3/) | OSPFv3 for IPv6 beside OSPFv2 (link-local neighbors, LSA types 8 and 9), and an OSPFv3 instance-ID mismatch | `17_ospfv3_dual_stack`, `18_ospfv3_instance_mismatch` | Both pass on the shared lab (run 2026-09-27); README has the captured output |

**What "Status" means.** Every lab uses the same four routers, addressing and baseline configurations as the shared lab, and the
same scenario files. All scenarios except `08_bfd` have passed apply and rollback against the shared lab on EVE-NG. The standalone
`.unl` files themselves (import, start, bootstrap through `labtool.sh`) have **not yet been run**; please report or fix anything
that differs, and record real output with `labtool.sh <lab> capture <scenario>`.

### What is in a lab folder

| File | What it is |
|---|---|
| `README.md` | The use case, topology, commands, what you should see, and production notes |
| `CONFIGS.md` | **Generated.** Links, every router's full configuration ready to paste, and each scenario's apply / rollback lines per router with its checks |
| `<lab>.unl` | The EVE-NG topology (**generated**). Same as `ospf-sla.unl` except the lab name and UUID |
| `<lab>.zip` | The `.unl` in a zip: the form EVE's web **Import** accepts |
| `inventory.yaml` | Devices, management addresses, router IDs, links and the variables the templates use |
| `baseline/*.cfg` | Full per-router configurations (copies of `backend/baseline/`) |
| `scenarios/*.yaml`, `templates/*.j2` | The lab's two scenarios: targets, variables, verify assertions, and the Jinja2 apply / rollback template |
| `probes.txt` | `ROUTER|show command` lines that `labtool.sh capture` runs before, after apply and after rollback |

## Running a lab

Run on the EVE-NG VM, from the repository checkout, after `docker compose up -d --build` has built the `ospf-sla-executor` image
(`labtool.sh` runs throwaway containers from it) and with a `.env` in the repository root. Make the script executable once
(`chmod +x labs/labtool.sh`) or call it with `bash labs/labtool.sh`.

```bash
labs/labtool.sh main stop ; docker stop ospf-sla-executor     # never run two labs at once (see below)

labs/labtool.sh 06_nssa up                    # import + start + bootstrap + baseline + health (about 10 minutes)
labs/labtool.sh 06_nssa health                # ping, SSH and FULL neighbors per router
labs/labtool.sh 06_nssa show R1 "show ip route ospf"
labs/labtool.sh 06_nssa apply    06_nssa      # push, wait settle_seconds, verify
labs/labtool.sh 06_nssa rollback 06_nssa
labs/labtool.sh 06_nssa capture  14_dual_nssa_translator   # probes before / after apply / after rollback
labs/labtool.sh 06_nssa baseline              # reset every router to baseline/*.cfg

labs/labtool.sh 06_nssa stop ; labs/labtool.sh main start ; docker start ospf-sla-executor
```

| Command | What it does |
|---|---|
| `import` | Copies `<lab>.unl` to `/opt/unetlab/labs/` (needs root on the VM) |
| `start` / `stop` | Starts or stops every node through the EVE-NG API |
| `bootstrap [NODE ...]` | One-time console bring-up: hostname, user, domain, RSA key, SSH, MGMT VRF and address |
| `baseline [NODE ...]` | Pushes `baseline/<NODE>.cfg`; also the way to reset the lab |
| `health` | Ping, SSH and the number of `FULL` neighbors per router |
| `apply` / `rollback <scenario>` | Runs a scenario of the lab with its verification and prints PASS / FAIL per check |
| `show <NODE> "<cmd>"` | One read-only command |
| `capture <scenario>` | The `probes.txt` commands before, after apply and after rollback |
| `up` | `import`, `start`, `bootstrap`, `baseline`, then `health` |

`main` in place of a lab name drives the shared lab (`/ospf-sla.unl`, files from `backend/`) with the same commands.

### One lab at a time

Every lab has the same node IDs and the same management addresses (192.168.99.11 to .14) as the shared lab, so:

* **Only one lab may run at a time.** EVE-NG keys Dynamips nodes by tenant and node ID, and two routers answering the same
  management address would receive each other's configuration.
* **Stop the dashboard first** (`docker stop ospf-sla-executor`). Its monitor polls the same addresses, and it uses the same EVE-NG
  account: EVE-NG keeps one session per account, so the dashboard and `labtool.sh` would log each other out.
* **A lab started for the first time boots blank.** `up` runs `bootstrap` and `baseline` for you. Allow a few minutes for the first boot.

## Building a lab by hand

Every lab folder has a generated `CONFIGS.md` with every router's configuration ready to paste on its console and the scenario
commands per router. Import `<lab>.zip` in the EVE-NG web UI, start the nodes, and paste. No tooling is needed.

## Regenerating the files

```bash
# CONFIGS.md of every lab (or one: add the lab name); needs PyYAML and Jinja2
python scripts/make-lab-configs.py

# a lab's .unl and .zip
python backend/scripts/build_lab.py --inventory labs/06_nssa/inventory.yaml --out labs/06_nssa/06_nssa.unl --zip

# the shared lab
python backend/scripts/build_lab.py --zip
```

The baselines, scenarios and templates in the lab folders are copies of those in `backend/`. When you change one in `backend/`,
copy it to the lab that uses it and regenerate that lab's `CONFIGS.md`.

## Adding a lab

1. Create `labs/NN_topic/` with `inventory.yaml` (copy one from another lab; change the `# Lab` title line, `lab.name` and
   `lab.uuid`), `baseline/`, `scenarios/`, `templates/` and `probes.txt`.
2. Write its `README.md`.
3. Generate `CONFIGS.md`, `.unl` and `.zip` as above, and add a row to the table at the top of this file.
