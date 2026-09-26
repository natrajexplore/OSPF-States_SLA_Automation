# Lab 01: Adjacency states, a neighbor that never reaches Full

**Use case.** Two routers share a link, both run OSPF, and yet `show ip ospf neighbor` never says `FULL`. This lab breaks the
R3-R4 adjacency in the two ways that cause most "stuck neighbor" tickets, and shows why they fail at different points of the
neighbor state machine (Down, Init, 2-Way, ExStart, Exchange, Loading, Full):

| Scenario | The mistake | Where the state machine stops |
|---|---|---|
| `01_adjacency` | R4's hello-interval is 5 s, R3's is 10 s | Before 2-Way: hello parameters must match, so each side drops the other's hellos |
| `09_mtu_mismatch` | R4's IP MTU is 1300, R3's is 1500 | ExStart / Exchange: hellos are fine, the DBD exchange fails |

## Topology

```
               area 0   10.0.123.0/24  broadcast segment (Ethernet1/0 on R1, R2, R3)
     R1 (prio 1)            R2 (prio 50, ABR)        R3 (prio 100, ABR)
     10.255.0.1             10.255.0.2               10.255.0.3
         |______________________|_________________________|
                                | e1/1 10.1.24.1          | e1/1 10.1.34.1
                     area 1 p2p | 10.1.24.0/30            | 10.1.34.0/30   area 1 p2p
                                | e1/1 10.1.24.2          | e1/0 10.1.34.2   <-- this lab breaks this link
                                |_________________________|
                                            R4  10.255.0.4 (area 1)
```

| Router | Role | Router ID / Lo0 | Management | Links |
|---|---|---|---|---|
| R1 | backbone | 10.255.0.1 (area 0) | 192.168.99.11 | e1/0 10.0.123.1/24 area 0 |
| R2 | ABR | 10.255.0.2 (area 0) | 192.168.99.12 | e1/0 10.0.123.2/24 area 0; e1/1 10.1.24.1/30 area 1 |
| R3 | ABR | 10.255.0.3 (area 0) | 192.168.99.13 | e1/0 10.0.123.3/24 area 0; e1/1 10.1.34.1/30 area 1 |
| R4 | area 1 | 10.255.0.4 (area 1) | 192.168.99.14 | e1/0 10.1.34.2/30 to R3; e1/1 10.1.24.2/30 to R2 |

Every router's full configuration, ready to paste, is in [`CONFIGS.md`](CONFIGS.md).

## Run it

On the EVE VM, from the repository checkout (stop the shared lab and the dashboard first, see [`../README.md`](../README.md#running-a-lab)):

```
labs/labtool.sh 01_adjacency up                       # import + start + bootstrap + baseline, about 10 minutes
labs/labtool.sh 01_adjacency show R3 "show ip ospf neighbor"
labs/labtool.sh 01_adjacency apply    01_adjacency    # hello 5 s on R4
labs/labtool.sh 01_adjacency rollback 01_adjacency
labs/labtool.sh 01_adjacency apply    09_mtu_mismatch # ip mtu 1300 on R4, then clear ip ospf process
labs/labtool.sh 01_adjacency rollback 09_mtu_mismatch
labs/labtool.sh 01_adjacency capture  09_mtu_mismatch # probes.txt before, after apply, after rollback
```

## What you should see

The lines below are what the automated verification checks (regexes in `scenarios/*.yaml`). Both scenarios passed apply and
rollback on the shared lab, which has the same routers and configuration. Record your own output with `capture`.

**Baseline.** R3 lists R4 as `FULL/  -` (no DR on a point-to-point link), and R4 lists R3 and R2 the same way.

**`01_adjacency` applied** (check after 60 s). R4 sends hellos every 5 s with a 20 s dead interval; R3 still expects 10/40.
The line `10.255.0.4 ... FULL` disappears from R3, and `10.255.0.3 ... FULL` from R4. Compare the timers on each side:

```
R4# show ip ospf interface Ethernet1/0      ... Timer intervals configured, Hello 5, Dead 20 ...
R3# show ip ospf interface Ethernet1/1      ... Timer intervals configured, Hello 10, Dead 40 ...
```

The R2-R4 link is untouched, so R4 still reaches area 0 through R2: a real network degrades, it does not go dark.

**`09_mtu_mismatch` applied** (check after 30 s). Hellos do not carry the MTU, so the neighbor is seen, but the database
description exchange rejects R3's packets as larger than R4's MTU. R3 shows R4 stuck in `EXSTART` or `EXCHANGE`, never `FULL`.
The scenario runs `clear ip ospf process` on R4, because the MTU is only checked while an adjacency forms: a Full adjacency does
not notice the change until the next time the link or process resets, which in production is often days later.

**Rollback.** Both scenarios restore the baseline value and the adjacency climbs back to `FULL`.

## Production notes

* **Timer mismatch:** hello and dead intervals must match on both ends. `show ip ospf interface` on both sides, or
  `debug ip ospf hello` (look for `Mismatched hello parameters`).
* **MTU mismatch:** the tell-tale sign is a neighbor that alternates between EXSTART and EXCHANGE. Fix the MTU. When one side
  cannot change (an odd-MTU provider circuit), `ip ospf mtu-ignore` skips the check, at the price of possible fragmentation.
* In Grafana the adjacency shows as a drop in `ospf_neighbor_state` for the R3-R4 pair and a rise of `ospf_neighbor_transitions_total`.

Learn more: dashboard **Learn** tab, topic *OSPF fundamentals*.
