# OSPF SLA & States Automation

A hands-on OSPF platform on **EVE-NG** with real Cisco IOS routers (7206VXR / c7200, Dynamips): pick a scenario, click **Apply**,
and the platform configures the routers over SSH, waits for OSPF to converge, verifies the result against regex assertions and
shows a before/after diff, while a live telemetry pipeline (Kafka, Prometheus, Grafana) records every adjacency change.

| Part | What it is | Where |
|---|---|---|
| **Dashboard** | React UI: live OSPF monitor, 16 scenarios with Apply / Rollback and streamed logs, lab control, Learn, Kafka and Prometheus tabs | `http://<eve-vm>:8082` |
| **Live 3D** | The lab in 3D with live adjacency colours; Apply / Rollback animates every SSH session (a beam per configuration line) next to the SSH / CLI transcript with the real IOS prompts | `#live`, [details](#live-3d-cli-credentials-and-putty) |
| **CLI and Credentials tabs** | Any whitelisted `show` on any router with a kept transcript; every router's login, password and enable secret (hidden until Reveal) for all 9 labs | `#cli`, `#credentials` |
| **PuTTY sessions** | One click on **SSH session** opens a router in its own PuTTY window, through the EVE VM (one-time `scripts\putty-setup.ps1`) | [PuTTY](#one-putty-window-per-router) |
| **16 scenarios** | 8 OSPF concepts (01-08) and, for each, the production failure that belongs to it (09-16), as YAML + Jinja2 with apply and rollback | [`backend/scenarios/`](backend/scenarios/), [`backend/templates/`](backend/templates/) |
| **8 standalone labs** | One folder per topic with a README, every router's configuration ready to paste, an EVE topology (`.unl` and `.zip`) and its two scenarios, driven by `labtool.sh` | [`labs/`](labs/) |
| **Learn tab** | A course on 8 OSPF topics at three levels (Beginner, Pro, Expert), each level unlocked by a short quiz; every topic has a 3D packet flow through the lab and a table of its OSPF parameters | `http://<eve-vm>:8082/#learn` |
| **Monitoring** | Poller to Kafka to a Prometheus exporter, Grafana dashboard *OSPF SLA & States* and 7 alert rules | [`monitoring/`](monitoring/) |

The design follows [BGP-Attributes-Executor-Automation_tools](https://github.com/natrajexplore/BGP-Attributes-Executor-Automation_tools):
each concept is a YAML scenario plus a Jinja2 template with an apply and a `{% if rollback %}` branch, verified by regex assertions,
and each topic also exists as a standalone lab folder.

---

## Start here

| I want to... | Go to |
|---|---|
| **Run a scenario** and watch OSPF react | the dashboard's **Live 3D** tab (3D + SSH transcript) or **Scenarios** tab, after the [Quick start](#quick-start) |
| **Open a router in its own PuTTY window** | **SSH session** on Live 3D, CLI or Credentials, after a one-time [PuTTY setup](#one-putty-window-per-router) |
| **Look up a router's login and enable secret** | the **Credentials** tab |
| **Read a router without PuTTY** | the **CLI** tab (`#cli/R3` opens R3 and runs `show ip ospf neighbor`) |
| **Learn** OSPF from the basics to production pitfalls | the dashboard's **Learn** tab: [Learn tab](#the-learn-tab) |
| **Build one topic's lab by hand** on the router consoles | [`labs/<lab>/CONFIGS.md`](#the-8-standalone-labs) (every router's configuration, ready to paste) |
| **Run one topic's lab with the tooling** (import, start, bootstrap, apply, rollback) | [`labs/labtool.sh`](labs/labtool.sh) and [`labs/README.md`](labs/README.md#running-a-lab) |
| **Import a lab into the EVE-NG web UI** | the `.zip` in each lab folder (EVE's Import rejects a bare `.unl`) |
| **Watch adjacencies in Grafana** | [Monitoring](#monitoring-kafka--prometheus--grafana) |
| **Look up addressing and the first-run checklist** | [`docs/lab.md`](docs/lab.md) |

---

## Architecture

```
Browser ──> nginx :8082 (ospf-sla-ui) ──/api, SSE──> FastAPI :8010 (ospf-sla-executor)
                                                    ├─ EVE-NG REST API        topology, node state, console ports
                                                    ├─ Netmiko SSH ──> 192.168.99.11-14 (MGMT VRF on Fa0/0, bridged via Cloud1 / pnet1)
                                                    ├─ scenario engine        Jinja2 render ─> push ─> settle ─> verify ─> diff
                                                    └─ poller (20 s) ──> Kafka :9094 ──> exporter :9108 ──> Prometheus :9090 ──> Grafana :3000
     both containers run on the EVE-NG VM (network_mode: host)            the monitoring stack runs on Docker Desktop (Windows)
```

* **Backend:** FastAPI, Netmiko, Jinja2. A scenario is a YAML file (targets, variables, `settle_seconds`, optional `post_commands`,
  `verify` and `rollback_verify` assertions) and one template. Scenarios with disjoint targets run concurrently; a run that needs a
  router another run is using is refused (`409 already running on: R4`).
* **Frontend:** React (Vite), served by nginx, which also proxies the API and the server-sent event streams. The 3D views use
  Three.js, bundled as a separate chunk that loads only when a 3D view opens.
* **Labs:** the EVE topology is generated from an `inventory.yaml` by `backend/scripts/build_lab.py`. The backend reads its
  inventory, baselines, scenarios and templates from environment variables (`OSPF_INVENTORY`, `OSPF_BASELINE`, `OSPF_SCENARIOS`,
  `OSPF_TEMPLATES`), which is how `labs/labtool.sh` drives any lab folder without code changes.

---

## The lab

Four routers, two areas, three links:

```
               area 0   10.0.123.0/24  broadcast segment (Ethernet1/0)         DR/BDR election happens here
     R1 (prio 1)            R2 (prio 50, ABR)        R3 (prio 100, ABR)
     10.255.0.1             10.255.0.2               10.255.0.3
         |______________________|_________________________|
                                | e1/1 10.1.24.1          | e1/1 10.1.34.1
                     area 1 p2p | 10.1.24.0/30            | 10.1.34.0/30   area 1 p2p
                                | e1/1 10.1.24.2          | e1/0 10.1.34.2
                                |_________________________|
                                            R4  10.255.0.4 (area 1)
                              Loopback1 10.4.4.1/24 (not in OSPF at baseline)
                              IP SLA 1: icmp-echo to R1's loopback every 10 s
```

| Router | Role | Router ID / Lo0 | Management (Fa0/0, VRF MGMT) |
|---|---|---|---|
| R1 | backbone | 10.255.0.1 | 192.168.99.11 |
| R2 | ABR | 10.255.0.2 | 192.168.99.12 |
| R3 | ABR | 10.255.0.3 | 192.168.99.13 |
| R4 | internal, area 1 | 10.255.0.4 | 192.168.99.14 |

At baseline R3 is the DR, R2 the BDR, R1 a DROTHER, and R4 reaches R1 over two equal-cost paths (through R3 and through R2).
Router login: user `lab`, password and enable secret `lab123` (set in [`backend/inventory.yaml`](backend/inventory.yaml) and `.env`).
Full addressing and the first-run checklist: [`docs/lab.md`](docs/lab.md). Configurations: [`backend/baseline/`](backend/baseline/).

---

## Scenarios

Each concept scenario (01-08) demonstrates a feature working; its production partner (09-16) demonstrates the mistake that shows
up in real incident reports. Every scenario has an apply and a rollback path with its own checks.

| Concept | Scenario: the feature | Scenario: the production failure | Watch in Grafana |
|---|---|---|---|
| Adjacency states | **01** R4 hello 5 s vs R3's 10 s: R3-R4 leave Full; rollback re-forms it | **09** R4 IP MTU 1300 vs 1500: hellos fine, the DBD exchange stalls in ExStart / Exchange | neighbor state timeline, transitions |
| DR/BDR election | **02** Priorities move the DR from R3 to R1 (`clear ip ospf process` forces the non-preemptive re-election) | **10** R4 `broadcast` vs R3 `point-to-point` on the same link: the adjacency never completes | interface roles, role changes |
| Multi-area / ABR | **03** R4 Lo1 enters area 1; the ABRs originate a type-3 LSA; R1 installs `O IA` | **11** R4's side of the link moved to area 0: hellos silently dropped, no adjacency | routes by type |
| Stub area | **04** `area 1 stub` on R2, R3, R4; R4 gets `O*IA 0.0.0.0/0` | **12** `area 1 stub` on R3 only: R3-R4 breaks while R2-R4 stays Full | adjacency bounce, routes by type |
| External routes | **05** R1 redistributes a static route; R3 and R4 get `O E2` (set `ext_metric_type: 1` for E1) | **13** `redistribute static` without `subnets`: accepted, logged nowhere, the route never appears | routes by type (`O E2`) |
| NSSA | **06** Area 1 NSSA; R4 injects Lo1 as type 7 (`O N2`), R3 translates it, R1 gets `O E2` | **14** `translate type7 always` on R2 silently takes translation away from R3, the elected translator | routes by type |
| Cost / path selection | **07** `ip ospf cost 100` on R4 e1/0: the equal-cost paths to R1 collapse to the one through R2 | **15** `auto-cost reference-bandwidth 10000` on R4 only: costs diverge, every neighbor stays Full | interface cost, IP SLA latency |
| Fast failure detection | **08** BFD on R3-R4 ⚠️ **wedges Dynamips, do not run** | **16** `dead-interval minimal hello-multiplier 4`: down in 1 s without BFD | neighbor state timeline |

**Combining scenarios.** 04 (stub) and 06 / 14 (NSSA) are mutually exclusive; 03, 06 and 14 all use R4's Loopback1; 05 and 13 both
configure `redistribute static` on R1. Roll one back before applying the other.

**Scenario 08 does not work on this platform.** Enabling BFD (at 50 ms and at 500 ms x 3) reliably wedges the IOS scheduler of
`c7200-adventerprisek9-mz.152-4.S6` under Dynamips: `%SCHED-5-INT_DISABLED_BEFORE_PREEMPTION` at the same internal address, then no
SSH, ping or console. It is a platform defect, not a configuration problem; real hardware does not hit it. Scenario 16 is the working
alternative. Failure signature and recovery: [`docs/lab.md`](docs/lab.md#first-run-checklist).

Add your own: [`docs/lab.md`](docs/lab.md#adding-a-scenario). Planned next: totally stubby areas, summarisation, virtual links,
authentication, OSPFv3.

---

## The 8 standalone labs

Each topic also exists as a self-contained folder in [`labs/`](labs/), pairing its concept scenario with its production failure.
A folder holds a `README.md` (use case, topology, commands, what you should see, production notes), a generated **`CONFIGS.md`**
(every router's full configuration and each scenario's lines per router, ready to paste), `<lab>.unl` and `<lab>.zip`,
`inventory.yaml`, `baseline/`, `scenarios/`, `templates/` and `probes.txt`.

| Lab | Topic | Scenarios | Open |
|---|---|---|---|
| **01** Adjacency | A neighbor that never reaches Full: timers vs MTU | `01_adjacency`, `09_mtu_mismatch` | [README](labs/01_adjacency/README.md) · [configs](labs/01_adjacency/CONFIGS.md) · [.zip](labs/01_adjacency/01_adjacency.zip) |
| **02** DR/BDR | Who owns the broadcast segment; network-type mismatch | `02_dr_bdr`, `10_network_type_mismatch` | [README](labs/02_dr_bdr/README.md) · [configs](labs/02_dr_bdr/CONFIGS.md) · [.zip](labs/02_dr_bdr/02_dr_bdr.zip) |
| **03** Multi-area | Type-3 summaries at the ABR; area-ID mismatch | `03_inter_area`, `11_area_mismatch` | [README](labs/03_inter_area/README.md) · [configs](labs/03_inter_area/CONFIGS.md) · [.zip](labs/03_inter_area/03_inter_area.zip) |
| **04** Stub area | A default instead of the full table; partial rollout | `04_stub_area`, `12_partial_stub_rollout` | [README](labs/04_stub_area/README.md) · [configs](labs/04_stub_area/CONFIGS.md) · [.zip](labs/04_stub_area/04_stub_area.zip) |
| **05** External routes | An ASBR and `O E2`; the `subnets` trap | `05_external_e2`, `13_subnets_keyword` | [README](labs/05_external_routes/README.md) · [configs](labs/05_external_routes/CONFIGS.md) · [.zip](labs/05_external_routes/05_external_routes.zip) |
| **06** NSSA | Type 7 to type 5; translator takeover | `06_nssa`, `14_dual_nssa_translator` | [README](labs/06_nssa/README.md) · [configs](labs/06_nssa/CONFIGS.md) · [.zip](labs/06_nssa/06_nssa.zip) |
| **07** Cost | Steering by cost; reference-bandwidth mismatch | `07_cost_steering`, `15_reference_bandwidth_mismatch` | [README](labs/07_cost_steering/README.md) · [configs](labs/07_cost_steering/CONFIGS.md) · [.zip](labs/07_cost_steering/07_cost_steering.zip) |
| **08** Fast convergence | Fast hellos; BFD for reference only | `08_bfd`, `16_fast_hello_no_bfd` | [README](labs/08_fast_convergence/README.md) · [configs](labs/08_fast_convergence/CONFIGS.md) · [.zip](labs/08_fast_convergence/08_fast_convergence.zip) |

The labs reuse the shared lab's four routers, addressing and baselines, so their scenarios are the ones already verified there. The
standalone `.unl` files have not yet been run through `labtool.sh` on EVE-NG; see [`labs/README.md`](labs/README.md) for status.

### Three ways to work with a lab

1. **By hand, from the router consoles.** Import `<lab>.zip` in the EVE-NG web UI, start the nodes, and paste each router's block
   from `CONFIGS.md`. Then try the scenario's apply lines, check, and roll back. Best for learning the configuration.
2. **With `labs/labtool.sh`** on the EVE VM. It runs throwaway containers from the dashboard image, pointed at the lab folder:

   ```bash
   labs/labtool.sh main stop ; docker stop ospf-sla-executor     # one lab at a time
   labs/labtool.sh 04_stub_area up                              # import + start + bootstrap + baseline + health
   labs/labtool.sh 04_stub_area apply    12_partial_stub_rollout
   labs/labtool.sh 04_stub_area rollback 12_partial_stub_rollout
   labs/labtool.sh 04_stub_area capture  04_stub_area           # show commands before / after apply / after rollback
   labs/labtool.sh 04_stub_area stop ; labs/labtool.sh main start ; docker start ospf-sla-executor
   ```

   All commands and the rules for switching labs: [`labs/README.md`](labs/README.md#running-a-lab).
3. **From the dashboard**, on the shared lab: every scenario of every topic is in the **Scenarios** tab.

**Only one lab can run at a time.** Every lab uses the same node IDs and management addresses (192.168.99.11 to .14), and the
dashboard's monitor polls those addresses and shares the EVE-NG account. Stop the shared lab and the dashboard before starting another lab.

---

## Quick start

1. **EVE-NG topology.** Generate the shared lab and import the zip in the EVE-NG web UI (details in [`docs/lab.md`](docs/lab.md#eve-ng-setup)):

   ```bash
   python backend/scripts/build_lab.py --zip        # -> labs/ospf-sla.unl and labs/ospf-sla.zip
   ```

   Adjust `image`, `idlepc` and `ram` in `backend/inventory.yaml` to your c7200 image first.

2. **Monitoring stack** (Docker Desktop on Windows):

   ```bash
   cp .env.example .env     # set KAFKA_ADVERTISED_HOST to the Windows IP the EVE VM can reach
   docker compose -f docker-compose.monitoring.yml up -d --build
   ```

   Allow inbound TCP 9094, 3000, 9090 and 8080 in Windows Firewall so the EVE VM and your browser can reach them.

3. **Backend and UI** (on the EVE-NG VM, with the same `.env`):

   ```bash
   docker compose up -d --build                                            # backend :8010, React UI :8082
   docker exec -it ospf-sla-executor python scripts/bootstrap.py           # once: hostname, SSH, MGMT on each router
   docker exec -it ospf-sla-executor python scripts/push_baseline.py       # OSPF baseline configurations
   docker exec -it ospf-sla-executor python scripts/healthcheck.py         # ping, SSH, FULL neighbors per router
   ```

4. **Open** `http://<eve-vm>:8082`.

The ports are 8010 / 8082 rather than 8000 / 8081 because a sibling EVE-NG project (the BGP executor) uses those on the same VM;
change them with `UI_PORT` and `API_UPSTREAM` in the `ospf-ui` service of [`docker-compose.yml`](docker-compose.yml).
UI development: `cd frontend && npm install && VITE_API=http://<eve-vm>:8010 npm run dev` (http://localhost:5173).

### `.env`

| Variables | What they set |
|---|---|
| `OSPF_EVENG_URL`, `OSPF_EVENG_USER`, `OSPF_EVENG_PASS`, `OSPF_LAB_PATH` | EVE-NG API access and the lab path (`/ospf-sla.unl`) |
| `OSPF_DEVICE_USER`, `OSPF_DEVICE_PASS`, `OSPF_DEVICE_SECRET` | Router login (must match the baselines) |
| `OSPF_CONSOLE_FALLBACK` | Use the EVE telnet console when SSH to a router fails |
| `KAFKA_ADVERTISED_HOST`, `OSPF_KAFKA_BOOTSTRAP`, `OSPF_POLL_INTERVAL` | Kafka listener and the backend's poller (empty bootstrap disables publishing) |
| `OSPF_GRAFANA_URL`, `OSPF_KAFKA_UI_URL`, `OSPF_PROMETHEUS_URL` | Links and queries used by the Lab, Kafka and Prometheus tabs |

`.env` is never committed; start from [`.env.example`](.env.example).

---

## The dashboard

| Tab | Address | What it is for |
|---|---|---|
| **Monitor** | `#monitor` | Per-router neighbors and states, DR/BDR roles, routes by type, BFD and IP SLA, and a live event feed (SSE) |
| **Live 3D** | `#live` | The lab in 3D with live adjacency colours, Apply / Rollback with SSH beams, the SSH / CLI transcript, and the EVE-NG and SSH card (**SSH session**, **CLI tab**) |
| **Scenarios** | `#scenarios` | Apply / Rollback with a streamed log, PASS / FAIL per check, and before/after diffs |
| **CLI** | `#cli`, `#cli/R3` | Whitelisted read-only `show` commands on any router, with a per-router transcript |
| **Lab** | `#lab` | Devices and their EVE-NG state, **Reset lab to baseline**, Grafana link |
| **Credentials** | `#credentials` | Login, password and enable secret of the 36 routers of the 9 labs, checked against their baselines, with **SSH session** buttons |
| **Learn** | `#learn` | The OSPF course with 3D packet flows and parameter tables, see below |
| **Kafka** | `#kafka` | The live stream of the three OSPF topics, and a link to Kafka UI |
| **Prometheus** | `#prometheus` | Live panels from Prometheus: router reachability, full adjacencies, interface cost, IP SLA, BFD |

### The Learn tab

Eight topics: OSPF fundamentals, DR/BDR election, areas, stub and NSSA areas, external routes and redistribution, cost and path
selection, fast convergence, and monitoring. Each topic has three levels, **Beginner**, **Pro** and **Expert**; passing the short
quiz at the end of a level unlocks the next one for that topic. Topics link to their scenarios in the Scenarios tab. Progress is
kept in your browser only.

Every topic also has a **See it in the lab** section, at every level:

* **A 3D packet flow** through the real lab (the same view as Live 3D, with live colours when the lab runs). A packet follows a path
  along the lab's links and stops at each router with a caption for that hop; the routers a scenario configures glow amber. Each topic
  has several flows: the baseline and what each of its scenarios changes. For example NSSA: R4's type-7 LSA → R3 translates it → R1
  installs `O E2`, and the takeover of scenario 14 where the same LSA goes through R2 instead.
* **A parameter table**: every OSPF parameter of the topic with its IOS command, its default, whether both ends must match, its
  value in this lab, and the scenario that changes it (hello / dead, area, MTU, network type, priority, stub / NSSA flags, translator,
  external metric and type, cost, reference bandwidth, fast hellos, BFD, IP SLA). Paths and tables are in
  [`frontend/src/learnLab.js`](frontend/src/learnLab.js).

### Live 3D, CLI, Credentials and PuTTY

**Live 3D** (`#live`) draws the shared lab: R1 on top, the ABRs R2 and R3 in the middle, R4 below, the area-0 and area-1 volumes (the
ABRs sit in both), the broadcast segment as a hub, and the SSH executor (the backend). Colours come from the monitor every 5 s: a link
end is green when the adjacency is FULL (or 2-WAY between DROTHERs), amber while it forms (INIT, EXSTART…), red when the neighbor is
lost; a router's ring is red when it stops answering. Orbit, zoom, **Rotate**, **Names**, **Light / Dark** (the 3D scene only, remembered
in the browser) and **Reset view**. Click a router to filter the transcript to it.

Pick a scenario and click **Apply** or **Rollback**: the target routers glow, each SSH session starts with a pulse, and each
configuration line travels as a beam from the executor to the router. The **SSH / CLI** panel shows the same session as it is typed:

```
$ ssh lab@192.168.99.14
R4#configure terminal
R4(config)#route-map LO1-ONLY permit 10
R4(config-route-map)#match interface Loopback1
R4(config)#router ospf 1
R4(config-router)#area 1 nssa
R4(config-router)#end
R4#write memory
R1#show ip route ospf      ! after check
```

The transcript is built from the run's event stream, so it needs no backend change. The verification (PASS / FAIL, before/after
diffs) is shown under it.

The **EVE-NG and SSH** card lists each router's EVE-NG state, SSH address, FULL neighbor count and two buttons: **SSH session** (its own
PuTTY window) and **CLI tab** (opens `#cli/<router>` and runs `show ip ospf neighbor`).

**CLI** (`#cli`) runs any command the backend allows (`show ip ospf …`, `show ip route …`, `show ip sla statistics`, `show bfd neighbors`,
`show running-config | section router ospf`) with one-click shortcuts, and keeps a transcript per router while the page is open.

**Credentials** (`#credentials`) lists the 36 routers of the shared lab and the 8 standalone labs: SSH address, user, password and
enable secret, hidden until **Reveal** (or **Reveal all**), with **Copy** and **SSH session**. Values come from each lab's
`inventory.yaml` (then `.env`), and each row says whether they match the `username` and `enable secret` lines of the router's baseline.
The dots only hide the values on screen: `GET /api/credentials` returns them to anyone who can open the dashboard, which is fine for a
private lab VM and worth remembering before exposing it. Today all 36 are `lab` / `lab123` / `lab123`.

### One PuTTY window per router

A web page cannot start programs, so **SSH session** uses an `ospfputty:<lab>/<router>` link, which a small handler installed once on
your PC turns into `putty.exe -load "OSPF <lab> <router>"` (your Windows user only, no administrator rights):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\putty-setup.ps1 -Server http://<eve-vm>:8082    # install
powershell -ExecutionPolicy Bypass -File scripts\putty-setup.ps1 -Server http://<eve-vm>:8082 -DryRun
powershell -ExecutionPolicy Bypass -File scripts\putty-setup.ps1 -Uninstall
```

* It reads the router list from `GET /api/credentials` and creates **36 saved sessions** named `OSPF <lab> <router>` (for example
  `OSPF shared R3`, `OSPF 06_nssa R4`), user `lab`, and registers the `ospfputty:` link. Run it again when labs are added.
* The management addresses 192.168.99.11-14 exist only inside the EVE VM, so each session goes **through the VM** with the Windows
  OpenSSH client (`ssh.exe -W %host:%port root@<eve-vm>`; change the user with `-JumpUser`). You need key login from your PC to the VM.
* The sessions offer only what the routers' IOS 15.2 SSH server supports (DH group14/group1, AES/3DES, RSA host keys). A 32-bit PuTTY
  starts the 64-bit `ssh.exe` through `C:\Windows\Sysnative`.
* **The password is never stored.** PuTTY asks for it (Credentials tab), then type `enable` and the enable secret.
* The first click makes the browser ask once to allow `ospfputty:` links. The first connection to a router shows PuTTY's host-key alert:
  click **Accept** (a router rebuilt from scratch has a new key, so the alert comes back).
* All labs share the same addresses, so a session reaches whichever lab is running; the lab id in the name and window title is a label.
* Without PuTTY, from any terminal: `ssh -J root@<eve-vm> -o KexAlgorithms=+diffie-hellman-group14-sha1 -o HostKeyAlgorithms=+ssh-rsa lab@192.168.99.13`.

### Command line

```bash
docker exec -it ospf-sla-executor python scripts/run_scenario.py apply    06_nssa
docker exec -it ospf-sla-executor python scripts/run_scenario.py rollback 06_nssa
docker exec -it ospf-sla-executor python scripts/run_scenario.py show R1 "show ip route ospf"
curl -X POST http://<eve-vm>:8010/api/scenarios/06_nssa/run
```

### HTTP API

| Endpoint | What it does |
|---|---|
| `GET /api/scenarios` | Every scenario with its full definition (title, summary, targets, vars, checks) |
| `POST /api/scenarios/{id}/run`, `POST /api/scenarios/{id}/rollback` | Apply or roll back; returns a `run_id` |
| `GET /api/runs/{run_id}`, `GET /api/stream/{run_id}` | A run's result, or its live log as server-sent events |
| `POST /api/lab/reset` | Push every baseline again |
| `GET /api/devices`, `GET /api/topology` | Routers with their EVE-NG state and console ports; the topology |
| `GET /api/graph` | Routers (tier, router ID, SSH address) and links (area, members) of the shared lab, for the 3D views |
| `GET /api/credentials` | Login, password and enable secret of every router of every lab, and whether each matches its baseline |
| `GET /api/devices/{name}/show?cmd=...` | A whitelisted read-only command (`show ip ospf ...`, `show ip route ...`, `show ip sla statistics`, `show bfd neighbors`) |
| `GET /api/monitor/state`, `GET /api/events/recent`, `GET /api/events/stream` | Monitor snapshot and the event feed |
| `GET /api/kafka/recent`, `GET /api/kafka/stream` | Recent and live Kafka messages |
| `GET /api/prometheus/query` | A Prometheus query, proxied for the Prometheus tab |
| `GET /api/health`, `GET /api/config` | Health check; the links configured in `.env` |

---

## Monitoring: Kafka → Prometheus → Grafana

```
scenario apply / rollback ─┐                                    ┌─> Prometheus :9090 ─> Grafana :3000
poller (20 s)  ────────────┴─> Kafka :9094 ─> exporter :9108 ───┘
(EVE VM backend)               (Docker Desktop on Windows)
```

| Topic | Content |
|---|---|
| `ospf.neighbor.events` | `neighbor_state_change`, `neighbor_lost`, `interface_role_change`, `router_(un)reachable` |
| `ospf.neighbor.snapshots` | Every poll: neighbors, interfaces (DR/BDR, cost, area), route counts by type, IP SLA |
| `ospf.config.changes` | Every scenario apply and rollback, and every baseline push |

**Metrics:** `ospf_neighbor_state` (0 Down to 7 Full), `ospf_neighbor_full`, `ospf_interface_role`, `ospf_interface_cost`,
`ospf_routes{type}`, `ospf_sla_rtt_milliseconds`, `ospf_sla_up`, `ospf_bfd_up`, `ospf_router_reachable`,
`ospf_neighbor_transitions_total`, `ospf_neighbor_lost_total`, `ospf_interface_role_changes_total`, `ospf_config_changes_total`.

**Alerts** ([`monitoring/prometheus/alerts.yml`](monitoring/prometheus/alerts.yml)): `OSPFNeighborNotFull`, `OSPFAdjacencyFlapping`,
`OSPFBFDSessionDown`, `OSPFSLAProbeFailing`, `OSPFSLALatencyHigh`, `OSPFRouterUnreachable`, `OSPFMonitorStale`.

Grafana: `http://localhost:3000`, dashboard *OSPF SLA & States*. Kafka UI: `http://localhost:8080`. Try it: apply scenario 01 and
watch the R3-R4 adjacency drop in the neighbor state timeline, the event in the Monitor feed and in Kafka UI, and
`OSPFNeighborNotFull` fire in Prometheus.

---

## Status

Run end-to-end against real EVE-NG / Dynamips routers and a live Kafka / Grafana stack: lab import, `bootstrap.py`,
`push_baseline.py`, `healthcheck.py`, full OSPF convergence, and scenarios **01-07 and 09-16** (apply and rollback) all pass.
The monitoring pipeline was confirmed live with real adjacency data. **Scenario 08 (BFD) does not work on this platform** (see above).
The 8 standalone lab folders reuse those verified configurations and scenarios; their `.unl` files have not yet been run through
`labtool.sh`.

The Live 3D, CLI and Credentials tabs, the Learn 3D views and the PuTTY sessions were checked against the live lab on 2026-09-27:
`/api/graph` and `/api/credentials` answer on the deployed dashboard (36 routers, every login matching its baseline); Live 3D and
Learn render with the real adjacency states; a rollback of scenario 01 run through the dashboard passed, and its real log produces
the expected SSH transcript; the CLI endpoint reads the routers; `putty-setup.ps1` created the 36 sessions, the `ospfputty:` link
opens the right PuTTY window, and the jump path through the VM reaches the routers' SSH server (`SSH-1.99-Cisco-1.25`).
Not yet exercised: clicking **Apply** in the Live tab in an interactive browser session, and a full PuTTY login (the password step).

---

## Repo layout

```
backend/
  app/              FastAPI application: scenario engine, devices (Netmiko), EVE-NG client, monitor, Kafka bus, validation,
                    labinfo (3D graph and the credentials of every lab; labs/ is mounted read-only at /app/labs)
  scenarios/        YAML: title, targets, vars, settle_seconds, post_commands, verify / rollback_verify
  templates/        Jinja2, one per scenario (apply + {% if rollback %}, branching on target where routers differ)
  baseline/         full per-router IOS configurations of the shared lab
  scripts/          build_lab.py, bootstrap.py, push_baseline.py, run_scenario.py, healthcheck.py
  inventory.yaml    devices, management IPs, router IDs, links, EVE node settings, template variables
frontend/           React UI served by nginx: Monitor, Live 3D, Scenarios, CLI, Lab, Credentials, Learn, Kafka, Prometheus
  src/topo3d.js     the Three.js scene (loaded on demand); Topo3D.jsx wraps it; liveState.js turns the monitor into colours
  src/learnLab.js   Learn tab: 3D packet flows and parameter tables per topic
labs/
  README.md         index, status and how to run the standalone labs
  labtool.sh        drive any lab: import, start, bootstrap, baseline, health, apply, rollback, show, capture, up
  ospf-sla.unl      the shared 4-router lab
  NN_<topic>/       README.md, CONFIGS.md, <lab>.unl, <lab>.zip, inventory.yaml, baseline/, scenarios/, templates/, probes.txt
scripts/
  make-lab-configs.py   generates every lab's CONFIGS.md
  putty-setup.ps1       one PuTTY session per router + the ospfputty: link (Windows, current user); putty-launch.ps1 opens one
docs/lab.md         addressing, EVE-NG setup, first-run checklist, production scenarios, adding a scenario
monitoring/         Kafka exporter, Prometheus configuration and alerts, Grafana dashboard and provisioning
```

## More documentation

* [`docs/lab.md`](docs/lab.md): addressing, EVE-NG setup, the first-run checklist (and the BFD recovery procedure), adding a scenario
* [`labs/README.md`](labs/README.md): the standalone labs, `labtool.sh`, one-lab-at-a-time rules, regenerating files
* Each lab's `README.md` and `CONFIGS.md`
