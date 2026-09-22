# Lab reference

## Addressing

| Router | Role | Router ID / Lo0 | MGMT (fa0/0, VRF MGMT) | e1/0 | e1/1 |
|---|---|---|---|---|---|
| R1 | backbone | 10.255.0.1 (area 0) | 192.168.99.11 | 10.0.123.1/24 area 0, Pri 1 | - |
| R2 | ABR | 10.255.0.2 (area 0) | 192.168.99.12 | 10.0.123.2/24 area 0, Pri 50 | 10.1.24.1/30 area 1, p2p |
| R3 | ABR | 10.255.0.3 (area 0) | 192.168.99.13 | 10.0.123.3/24 area 0, Pri 100 | 10.1.34.1/30 area 1, p2p |
| R4 | area 1 | 10.255.0.4 (area 1) | 192.168.99.14 | 10.1.34.2/30 area 1, p2p | 10.1.24.2/30 area 1, p2p |

R4 also has `Loopback1 10.4.4.1/24` (not in OSPF at baseline, used by scenario 03) and `ip sla 1`
(icmp-echo to 10.255.0.1 from Lo0, every 10 s). The single source of truth is
[`backend/inventory.yaml`](../backend/inventory.yaml); the baselines are in [`backend/baseline/`](../backend/baseline/).
Baseline DR/BDR: **R3 = DR, R2 = BDR, R1 = DROTHER** (set by priorities).

## EVE-NG setup

1. `python backend/scripts/build_lab.py` writes `labs/ospf-sla.unl` (4 c7200 nodes, `AREA0-LAN` shared bridge, `R3--R4` and `R2--R4` bridges, Cloud1 for MGMT).
   The `image`, `idlepc`, `ram` in `inventory.yaml` are copied from the BGP repo: adjust them to your EVE image.
2. EVE-NG *Import* accepts a zip: put the `.unl` at the top level of a zip file and import it.
3. Start the nodes, then run `scripts/bootstrap.py` (console: hostname, user, RSA key, SSH, MGMT), then `scripts/push_baseline.py`.
4. MGMT: Cloud1 (pnet1) must be bridged to a network where `192.168.99.0/24` is reachable from the backend container
   (gateway `192.168.99.1` in the inventory).

## First-run checklist

Untested-on-hardware assumptions worth confirming the first time:

- [ ] `show ip ospf neighbor` on R3 shows R1 and R2 as `FULL/DROTHER`/`FULL/BDR` and R4 as `FULL/  -`
- [ ] `no ip ospf 1 area` on R4 Lo1 is accepted by your IOS (baseline reset uses it; if not, use `no ip ospf 1 area 1`)
- [ ] `ip sla` is present in your c7200 image; `show ip sla statistics` prints `Latest RTT: N milliseconds`
- [ ] Scenario 02: R1 `DR`, R2 `BDR`, R3 `DROTHER` within `settle_seconds` (90 s; the wait timer alone is 40 s)
- [ ] Baseline: R4 has two equal-cost routes to 10.255.0.1 (`show ip route 10.255.0.1` lists 10.1.34.1 and 10.1.24.1)
- [ ] Scenario 06: c7200 image supports `area 1 nssa` and `match interface` in the route-map; R3 (highest router-id) translates 7 to 5
- [x] Scenario 08: **broken on this platform at any BFD interval — do not run it.** `bfd interval` + `ip ospf bfd`
      are accepted syntactically, but pushing them (even before any adjacency-level negotiation) reliably wedges
      the IOS scheduler: `%SCHED-5-INT_DISABLED_BEFORE_PREEMPTION`, always at the same internal EPC
      (`0x6308BEDC`), via whatever process happens to be scheduled next (`BFD PP Process`, `IP SLAs XOS Event
      Processor`, `SSS Feature Timer` were all seen) — the router stops answering SSH/ICMP/console entirely.
      Tested at both 50 ms and 500 ms/min_rx/x3 (`vars` in `08_bfd.yaml`); both wedged within seconds. This is a
      scheduler defect in this `c7200-adventerprisek9-mz.152-4.S6` image under Dynamips CPU contention, not a
      timer-speed or config problem — slower intervals do not help. Real hardware would not hit this.
      Recovery (needed twice during testing): stop the wedged node(s) in EVE-NG; if only one peer is wedged, shut
      the healthy peer's interface *before* restarting the wedged one, or the adjacency reforms and re-wedges it
      within the same boot; if both are wedged, start them one at a time with the other still stopped. A
      mid-crash push can also corrupt NVRAM back to factory default (happened to R4 twice) — if the router comes
      back as `Router#` instead of its hostname, re-run `bootstrap.py` then `push_baseline.py` for that node.
      After any recovery, check for a leftover `bfd interval ...` line on the interface even after `push_baseline`
      — baseline only sends `no ip ospf bfd`, not `no bfd interval ...`, so remove it by hand if present.
- [ ] Prometheus target `exporter:9108` is UP and `ospf_neighbor_state` has series
- [ ] Grafana dashboard *OSPF SLA & States* loads (Prometheus datasource uid `prom`)
- [ ] The `Scenario runs` annotation query renders in Grafana 11.3 (nice-to-have; drop it from `ospf.json` if it misbehaves)

## Production scenarios (09-16)

One realistic production failure mode per concept (01-08), same yaml+j2 pattern, run against the same 4-router lab.
Unlike 01-08 (which demonstrate a *feature*), these demonstrate a *mistake* - the kind that actually shows up in
network incident reports - so several intentionally verify that something is **missing** on apply (`must_not_match`)
and reappears on rollback, rather than the other way around.

| # | Concept | Production failure mode |
|---|---|---|
| 09 | MTU mismatch | R4's IP MTU drops to 1300 vs R3's 1500 - hellos match, DBD exchange fails, adjacency stalls before Full |
| 10 | Network type mismatch | R4 forced to `broadcast` while R3 stays `point-to-point` on the same link - adjacency never completes |
| 11 | Area mismatch | R4's interface moved to area 0 while R3 stays in area 1 - hellos silently dropped, no adjacency at all |
| 12 | Partial stub rollout | Only R3 gets `area 1 stub` (not R2/R4 together) - R3-R4 breaks, R2-R4 (separate link) stays up |
| 13 | Missing `subnets` keyword | `redistribute static` without `subnets` silently drops a subnetted prefix - no error, route just never appears |
| 14 | Translator takeover | Forcing `translate type7 always` on R2 (not the elected ABR) silently bypasses R3, the properly elected higher-router-id translator |
| 15 | Reference-bandwidth mismatch | R4 alone raises `auto-cost reference-bandwidth` - costs silently diverge from R1/R2/R3 while every neighbor stays Full |
| 16 | Fast hello (no BFD) | `ip ospf dead-interval minimal hello-multiplier 4` - sub-second-ish failure detection without touching BFD at all |

Interaction notes: 14 reuses R4's Loopback1/route-map like 03 and 06 - roll those back first. 13 and 05 both set
`redistribute static` on R1 - only one is active at a time.

## Adding a scenario

1. `backend/templates/NN_name.j2`: branch on `rollback` and, when several routers are targeted, on `target`.
2. `backend/scenarios/NN_name.yaml`: `title`, `concept`, `template`, `targets`, optional `post_commands` and `settle_seconds`,
   `verify` (regex per device/command; rollback defaults to the inverse, or give `rollback_verify`).
3. Put regexes in **single-quoted** YAML scalars so `\.` and `\s` are not treated as escapes.
