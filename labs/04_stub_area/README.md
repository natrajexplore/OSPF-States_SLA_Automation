# Lab 04: Stub area, a default route instead of the full table

**Use case.** Area 1 is a leaf of the network: it has one kind of exit (toward area 0) and does not need every external route.
Making it a **stub area** keeps type-5 external LSAs out and has the ABRs inject a default route instead. The stub flag travels
in every hello, so every router in the area must agree; this lab shows the change done right, and done on one router only.

| Scenario | What changes | What it demonstrates |
|---|---|---|
| `04_stub_area` | `area 1 stub` on R2, R3 and R4 together | The ABRs inject `O*IA 0.0.0.0/0`; externals disappear from area 1 |
| `12_partial_stub_rollout` | `area 1 stub` on R3 only | R3-R4 breaks, R2-R4 stays up: an asymmetric, partial outage |

## Topology

```
               area 0   10.0.123.0/24  broadcast segment (Ethernet1/0)
     R1                     R2 (ABR)                 R3 (ABR)
     10.255.0.1             10.255.0.2               10.255.0.3
         |__________________|________________________|
                            | 10.1.24.0/30           | 10.1.34.0/30   area 1 (stub in this lab)
                            |________________________|
                                        R4  10.255.0.4 (area 1)
```

| Router | Role | Router ID | Management | Area 1 links |
|---|---|---|---|---|
| R1 | backbone | 10.255.0.1 | 192.168.99.11 | - |
| R2 | ABR | 10.255.0.2 | 192.168.99.12 | e1/1 10.1.24.1/30 |
| R3 | ABR | 10.255.0.3 | 192.168.99.13 | e1/1 10.1.34.1/30 |
| R4 | internal, area 1 | 10.255.0.4 | 192.168.99.14 | e1/0 10.1.34.2/30, e1/1 10.1.24.2/30 |

Full configurations: [`CONFIGS.md`](CONFIGS.md).

## Run it

```
labs/labtool.sh 04_stub_area up
labs/labtool.sh 04_stub_area apply    04_stub_area
labs/labtool.sh 04_stub_area show R4 "show ip route ospf"
labs/labtool.sh 04_stub_area rollback 04_stub_area
labs/labtool.sh 04_stub_area apply    12_partial_stub_rollout
labs/labtool.sh 04_stub_area show R2 "show ip ospf neighbor"
labs/labtool.sh 04_stub_area rollback 12_partial_stub_rollout
```

## What you should see

These are the lines the automated verification checks; both scenarios passed apply and rollback on the shared lab.

**`04_stub_area` applied** (check after 60 s). The adjacencies in area 1 bounce while the three routers change the flag one after
the other, then come back `FULL`. R4 now has a default route from the ABRs:

```
R4# show ip route ospf        O*IA  0.0.0.0/0 [110/...] via 10.1.34.1 ... / via 10.1.24.1 ...
R3# show ip ospf neighbor     10.255.0.4   ...   FULL/  -   ...
```

Rollback removes the flag on all three routers; the default route disappears.

**`12_partial_stub_rollout` applied** (check after 40 s). Only R3 is stub. Its hellos on the R3-R4 link carry a different
options field (the E-bit) from R4's, so that adjacency drops: R3 no longer lists `10.255.0.4 ... FULL`. R2's link to R4 is a
separate segment and stays `FULL` the whole time, so R4 still reaches area 0 through R2 and the outage is easy to miss.
Rollback removes the flag from R3.

## Production notes

* Change the area type on **all** routers of the area in one change window. Push to the ABRs and the internal routers together
  (the automation here pushes to all targets in parallel) and expect the adjacencies to bounce once.
* Try it with lab 05: while area 1 is stub, R4 no longer has the external `O E2` route, only the default.
* `area 1 stub no-summary` on the ABRs (a *totally stubby* area) would also remove the inter-area routes and leave only the default.
* A stub area cannot contain an ASBR; that is what an NSSA is for (lab 06). Roll back `04_stub_area` before running lab 06's scenarios on the same routers.

Learn more: dashboard **Learn** tab, topic *Stub and NSSA areas*.
