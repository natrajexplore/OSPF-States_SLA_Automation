# Lab 03: Multi-area and the ABR, type-3 summaries and area IDs

**Use case.** A two-area design: area 0 is the backbone, area 1 hangs off two Area Border Routers (R2 and R3). A new prefix in
area 1 must reach the backbone as an inter-area route, and both ends of every link must agree on which area they are in.

| Scenario | What changes | What it demonstrates |
|---|---|---|
| `03_inter_area` | R4 advertises Loopback1 10.4.4.0/24 into area 1 | The ABR turns an area-1 route into a type-3 summary LSA; R1 installs `O IA` |
| `11_area_mismatch` | R4's side of the R3-R4 link moved to area 0, R3 stays in area 1 | An area-ID mismatch silently drops hellos: no adjacency, no error on the interface |

## Topology

```
               area 0   10.0.123.0/24  broadcast segment (Ethernet1/0)
     R1                     R2 (ABR)                 R3 (ABR)
     10.255.0.1             10.255.0.2               10.255.0.3
     (sees 10.4.4.0/24      |                        | originates the type-3 LSA
      as O IA)              |                        |
         |__________________|________________________|
                            | 10.1.24.0/30           | 10.1.34.0/30   area 1, point-to-point
                            |________________________|
                                        R4  10.255.0.4 (area 1)
                                        Loopback1 10.4.4.1/24   <-- added to area 1 by scenario 03
```

| Router | Role | Router ID | Management | Area 1 links |
|---|---|---|---|---|
| R1 | backbone | 10.255.0.1 | 192.168.99.11 | - |
| R2 | ABR | 10.255.0.2 | 192.168.99.12 | e1/1 10.1.24.1/30 |
| R3 | ABR | 10.255.0.3 | 192.168.99.13 | e1/1 10.1.34.1/30 |
| R4 | internal, area 1 | 10.255.0.4 | 192.168.99.14 | e1/0 10.1.34.2/30, e1/1 10.1.24.2/30; Lo1 10.4.4.1/24 |

Full configurations: [`CONFIGS.md`](CONFIGS.md).

## Run it

```
labs/labtool.sh 03_inter_area up
labs/labtool.sh 03_inter_area apply    03_inter_area
labs/labtool.sh 03_inter_area show R1 "show ip route ospf"
labs/labtool.sh 03_inter_area rollback 03_inter_area
labs/labtool.sh 03_inter_area apply    11_area_mismatch
labs/labtool.sh 03_inter_area rollback 11_area_mismatch
```

## What you should see

These are the lines the automated verification checks; both scenarios passed apply and rollback on the shared lab.

**`03_inter_area` applied** (check after 35 s). R4's Loopback1 goes into area 1 with `ip ospf network point-to-point`, so it
is advertised as a /24 (a loopback is otherwise advertised as a /32 host route). The ABR builds a summary LSA:

```
R3# show ip ospf database summary 10.4.4.0      ... Link State ID: 10.4.4.0 (summary Network Number) ...
R1# show ip route ospf                          O IA     10.4.4.0/24 [110/...] via 10.0.123.x ...
```

Both ABRs originate a type-3 LSA for the prefix. Rollback removes Loopback1 from OSPF and the `O IA` route is withdrawn.

**`11_area_mismatch` applied** (check after 30 s). Every hello carries the area ID. R3 receives hellos for area 0 on an area-1
interface and discards them, so `10.255.0.4 ... FULL` disappears from R3's neighbor table. Nothing in `show interface` hints at
the cause; only `debug ip ospf adj` shows the mismatched area. Rollback puts R4's interface back in area 1.

## Production notes

* Area renumbering or moving an area boundary must be done on **both** ends of each link in the same change window. Moving one
  router at a time produces exactly the silent outage of scenario 11.
* The ABR's type-3 LSAs are where inter-area summarisation (`area 1 range`) would go; the lab keeps them unsummarised so each prefix is visible.
* Do not run `03_inter_area` together with `06_nssa` or `14_dual_nssa_translator` (labs 06): all three use R4's Loopback1.

Learn more: dashboard **Learn** tab, topic *Areas and LSA types*.
