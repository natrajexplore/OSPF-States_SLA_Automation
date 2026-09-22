# OSPF SLA & States Automation

Hands-on OSPF on **EVE-NG** (Cisco 7206VXR / c7200, Dynamips) with event-driven telemetry:

```
FastAPI backend (on the EVE-NG VM, network_mode: host)
   ├─ EVE-NG REST API        topology, node state, console ports
   ├─ React UI (nginx :8082 default, proxies /api and SSE to the backend on :8010)
   ├─ Netmiko SSH ─> 192.168.99.0/24 (MGMT VRF on fa0/0, bridged via Cloud1/pnet1)
   └─ poller (20 s) ─> Kafka :9094 ─> exporter :9108 ─> Prometheus :9090 ─> Grafana :3000
```

Pattern taken from [BGP-Attributes-Executor-Automation_tools](https://github.com/natrajexplore/BGP-Attributes-Executor-Automation_tools):
each concept is a YAML scenario + a Jinja2 template with an apply and a rollback branch, and regex verify assertions.

## Lab (4 routers, 3 links)

```
      R1 (Pri 1)     R2 (Pri 50, ABR)   R3 (Pri 100, ABR)      area 0  10.0.123.0/24 broadcast
         └──────────────┴─────────┬────────┘
                                  │ e1/1 10.1.24.0/30    │ e1/1 10.1.34.0/30     both p2p, area 1
                                  └──────────┬───────────┘
                                             R4  (Lo1 10.4.4.0/24 not in OSPF; IP SLA 1 -> R1 loopback)
```
Router IDs `10.255.0.1-4`, MGMT `192.168.99.11-14`. Full detail: [`docs/lab.md`](docs/lab.md).

## Scenarios

| # | Concept | What happens | Watch in Grafana |
|---|---|---|---|
| 01 | Adjacency states | R4 hello-interval 5 vs R3's 10: R3-R4 leave Full; rollback re-forms it | neighbor state timeline, transitions |
| 02 | DR/BDR election | Priorities move DR from R3 to R1 (`clear ip ospf process` forces the non-preemptive re-election) | interface roles, role-change counter |
| 03 | Multi-area / ABR | R4 Lo1 goes into area 1; R3 originates a type-3 LSA; R1 gets `O IA` | routes by type |
| 04 | Stub area | `area 1 stub` on R3+R4; ABR injects a default, R4 gets `O*IA 0.0.0.0/0` | adjacency bounce, routes by type |
| 05 | External E2 / ASBR | R1 redistributes a static route; R3/R4 get `O E2` (change `ext_metric_type` for E1) | routes by type (`O E2`) |
| 06 | NSSA | area 1 NSSA on R2/R3/R4; R4 injects Lo1 as type 7 (`O N2`), R3 translates it to type 5, R1 gets `O E2` | routes by type, adjacency bounce |
| 07 | Cost / steering | `ip ospf cost 100` on R4 e1/0: the ECMP paths to R1 collapse to the R2 path | interface cost, IP SLA latency |
| 08 | BFD ⚠️ broken on Dynamips | BFD on R3-R4 registered with OSPF; sub-second failure detection | BFD state, neighbor state timeline |

Order/interaction notes: 04 (stub) and 06 (NSSA) are mutually exclusive, and 03 and 06 both use R4 Lo1, so roll one back before
applying the other. Planned next: totally-stubby, reference-bandwidth, summarization, virtual links, authentication, OSPFv3.

**Scenario 08 does not work on Dynamips.** Enabling BFD (tried at both 50ms and 500ms/x3 intervals) reliably wedges the
IOS scheduler on `c7200-adventerprisek9-mz.152-4.S6` under Dynamips CPU contention — `%SCHED-5-INT_DISABLED_BEFORE_PREEMPTION`
at the same internal fault address regardless of which process triggers it, and the router stops answering SSH/ICMP/console.
This is a platform defect, not a timer-speed or config issue; real hardware would not hit it. See the
[first-run checklist](docs/lab.md#first-run-checklist) for the full failure signature and the recovery procedure if you hit it.

## Quick start

1. **EVE-NG:** generate and import the topology, see [`docs/lab.md`](docs/lab.md#eve-ng-setup)
   ```
   python backend/scripts/build_lab.py          # -> labs/ospf-sla.unl  (zip it before importing)
   ```
2. **Monitoring stack** (Docker Desktop on Windows):
   ```
   cp .env.example .env     # set KAFKA_ADVERTISED_HOST to the Windows IP the EVE VM can reach
   docker compose -f docker-compose.monitoring.yml up -d --build
   ```
   Grafana http://localhost:3000 (dashboard *OSPF SLA & States*), Prometheus :9090, Kafka UI :8080.
3. **Backend** (on the EVE-NG VM, with the same `.env`):
   ```
   docker compose up -d --build          # backend :8010 and the React UI :8082
   docker exec -it ospf-sla-executor python scripts/bootstrap.py       # once: SSH + MGMT on each router
   docker exec -it ospf-sla-executor python scripts/push_baseline.py   # OSPF baseline configs
   docker exec -it ospf-sla-executor python scripts/healthcheck.py
   ```
4. **Open the UI:** `http://<eve-vm>:8082`
   - **Monitor**: per-router neighbors, DR/BDR roles, routes by type, BFD and IP SLA, plus a live event feed (SSE).
   - **Scenarios**: Apply / Rollback with a streamed log, PASS/FAIL verification and before/after diffs.
   - **Lab**: devices from EVE-NG, *Reset lab to baseline*, Grafana link.

   UI development: `cd frontend && npm install && VITE_API=http://<eve-vm>:8010 npm run dev` (http://localhost:5173).
   Change the port or backend with `UI_PORT` / `API_UPSTREAM` in the `ospf-ui` service of `docker-compose.yml`
   (default here is 8010/8082, not 8000/8081, because those were already taken by another EVE-NG project on the
   test host — see `docker-compose.yml`'s comment).
5. **Or run a scenario from the CLI:**
   ```
   docker exec -it ospf-sla-executor python scripts/run_scenario.py apply    01_adjacency
   docker exec -it ospf-sla-executor python scripts/run_scenario.py rollback 01_adjacency
   # or: curl -X POST http://<eve-vm>:8010/api/scenarios/01_adjacency/run
   ```

API: `/api/scenarios`, `/api/scenarios/{id}/run|rollback`, `/api/lab/reset`, `/api/runs/{id}`, `/api/stream/{id}` (SSE),
`/api/monitor/state`, `/api/events/stream`, `/api/devices/{name}/show?cmd=...` (whitelisted read-only).

## Kafka topics and metrics

| Topic | Content |
|---|---|
| `ospf.neighbor.events` | `neighbor_state_change`, `neighbor_lost`, `interface_role_change`, `router_(un)reachable` |
| `ospf.neighbor.snapshots` | per poll: neighbors, interfaces (DR/BDR, cost, area), route counts by type, IP SLA |
| `ospf.config.changes` | every scenario apply/rollback/baseline push |

Prometheus: `ospf_neighbor_state` (0 Down … 7 Full), `ospf_neighbor_full`, `ospf_interface_role`, `ospf_interface_cost`,
`ospf_routes{type}`, `ospf_sla_rtt_milliseconds`, `ospf_sla_up`, `ospf_neighbor_transitions_total`, `ospf_config_changes_total`.
Alerts in [`monitoring/prometheus/alerts.yml`](monitoring/prometheus/alerts.yml).

## Status

Run end-to-end against real EVE-NG/Dynamips routers and a live Kafka/Grafana stack: lab import, `bootstrap.py`,
`push_baseline.py`, `healthcheck.py`, full OSPF convergence, and scenarios 01-07 (apply + rollback, both directions)
all pass. The monitoring pipeline (poller → Kafka → exporter → Prometheus → Grafana) confirmed live with real
adjacency data. Scenario 08 (BFD) does not work on this platform — see the table above and
[`docs/lab.md`](docs/lab.md#first-run-checklist) for the failure signature and recovery procedure.
