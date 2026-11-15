# Lab 07: Cost, steering traffic and the reference-bandwidth trap

**Use case.** OSPF picks the path with the lowest total cost. At baseline R4 has two equal paths to R1 (through R3 and through
R2) and load-shares between them. Raising one link's cost moves the traffic; changing how costs are *computed* on only one
router makes routers disagree about the network without any alarm.

| Scenario | What changes | What it demonstrates |
|---|---|---|
| `07_cost_steering` | `ip ospf cost 100` on R4 Ethernet1/0 (the link to R3) | The two equal-cost paths collapse to the one through R2 |
| `15_reference_bandwidth_mismatch` | `auto-cost reference-bandwidth 10000` on R4 only | Costs silently diverge between routers while every neighbor stays `FULL` |

## Topology

```
               area 0   10.0.123.0/24  broadcast segment (Ethernet1/0)
     R1  (IP SLA target)    R2 (ABR)                 R3 (ABR)
     10.255.0.1             10.255.0.2               10.255.0.3
         |__________________|________________________|
                            | 10.1.24.0/30           | 10.1.34.0/30   cost 10 each at baseline
                            | (path 2)               | (path 1, cost 100 after scenario 07)
                            |________________________|
                                        R4  10.255.0.4
                                        IP SLA 1: icmp-echo to 10.255.0.1 every 10 s
```

| Router | Role | Router ID | Management |
|---|---|---|---|
| R1 | backbone, IP SLA target | 10.255.0.1 | 192.168.99.11 |
| R2 | ABR, path 2 | 10.255.0.2 | 192.168.99.12 |
| R3 | ABR, path 1 | 10.255.0.3 | 192.168.99.13 |
| R4 | area 1, IP SLA source | 10.255.0.4 | 192.168.99.14 |

Full configurations: [`CONFIGS.md`](CONFIGS.md).

## Run it

```
labs/labtool.sh 07_cost_steering up
labs/labtool.sh 07_cost_steering show R4 "show ip route 10.255.0.1"
labs/labtool.sh 07_cost_steering apply    07_cost_steering
labs/labtool.sh 07_cost_steering rollback 07_cost_steering
labs/labtool.sh 07_cost_steering apply    15_reference_bandwidth_mismatch
labs/labtool.sh 07_cost_steering show R4 "show ip ospf interface brief"
labs/labtool.sh 07_cost_steering rollback 15_reference_bandwidth_mismatch
```

## What you should see

These are the lines the automated verification checks; both scenarios passed apply and rollback on the shared lab.

**Baseline.** Two equal-cost next hops:

```
R4# show ip route 10.255.0.1
  ... 10.1.34.1, from 10.255.0.1, ... via Ethernet1/0
  ... 10.1.24.1, from 10.255.0.1, ... via Ethernet1/1
```

**`07_cost_steering` applied** (check after 15 s). Only `10.1.24.1, from` remains; `10.1.34.1, from` is gone. The IP SLA probe
from R4 keeps succeeding over the new path, and `ospf_interface_cost` in Grafana shows the step to 100. The `steer_cost` value is
a variable in `scenarios/07_cost_steering.yaml`. Rollback restores cost 10 and both next hops return.

**`15_reference_bandwidth_mismatch` applied** (check after 15 s). `show ip ospf` on R4 says
`Reference bandwidth unit is 10000 mbps`; R1, R2 and R3 still use 100. IOS prints a local warning at most, and no adjacency
moves. Note what does **not** change in this lab: R4's area-1 links have an explicit `ip ospf cost 10`, and a loopback costs 1 at
either reference value, so `show ip ospf interface brief` shows the same costs. That is the point of the scenario: the only trace
is one line in `show ip ospf`. On a network with automatic (bandwidth-derived) costs, R4 would now compute costs 100 times higher
than its neighbors and choose paths they disagree with. Rollback restores 100.

## Production notes

* The default reference bandwidth (100 Mb/s) gives 100 Mb/s, 1 Gb/s and 10 Gb/s links the **same** cost of 1. Raise it, but on
  **every** router in the same change, and prefer explicit `ip ospf cost` on links whose cost you care about.
* Steering with cost is visible to the whole area: adding 90 on one link changes every path that crossed it. Check the result
  with `show ip route` on the routers whose traffic you meant to move, and on some you did not.
* Grafana: `ospf_interface_cost` and the IP SLA RTT panel (`ospf_sla_rtt_milliseconds`) show the move.

Learn more: dashboard **Learn** tab, topic *Cost and path selection*.
