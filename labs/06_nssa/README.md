# Lab 06: NSSA, type 7 in the area and one translator at the edge

**Use case.** Area 1 should keep external routes from the rest of the network out (like a stub area), but a router inside it,
R4, has an external network of its own to announce. That is a **Not-So-Stubby Area**: R4 originates a type-7 LSA, and one ABR
translates it into a type-5 LSA for the backbone. With two ABRs, which one translates is decided by election, unless someone overrides it.

| Scenario | What changes | What it demonstrates |
|---|---|---|
| `06_nssa` | `area 1 nssa` on R2, R3, R4; R4 redistributes Loopback1 10.4.4.0/24 | Type 7 inside the area (`O N2`), translated to type 5 by R3 (`O E2` on R1) |
| `14_dual_nssa_translator` | The same NSSA, plus `area 1 nssa translate type7 always` on R2 | R2 takes over translation from R3, the elected translator, without any error |

## Topology

```
               area 0   10.0.123.0/24  broadcast segment (Ethernet1/0)
     R1                     R2 (ABR)                 R3 (ABR, highest router ID = elected translator)
     10.255.0.1             10.255.0.2               10.255.0.3
     (sees O E2)            |                        |
         |__________________|________________________|
                            | 10.1.24.0/30           | 10.1.34.0/30   area 1 = NSSA in this lab
                            |________________________|
                                        R4  10.255.0.4 (area 1, ASBR in this lab)
                                        Loopback1 10.4.4.1/24  -> redistributed connected, type 7
```

| Router | Role in this lab | Router ID | Management |
|---|---|---|---|
| R1 | backbone | 10.255.0.1 | 192.168.99.11 |
| R2 | ABR (translator in scenario 14) | 10.255.0.2 | 192.168.99.12 |
| R3 | ABR (elected translator in scenario 06) | 10.255.0.3 | 192.168.99.13 |
| R4 | NSSA ASBR | 10.255.0.4 | 192.168.99.14 |

Full configurations: [`CONFIGS.md`](CONFIGS.md).

## Run it

```
labs/labtool.sh 06_nssa up
labs/labtool.sh 06_nssa apply    06_nssa
labs/labtool.sh 06_nssa show R1 "show ip ospf database external"
labs/labtool.sh 06_nssa rollback 06_nssa
labs/labtool.sh 06_nssa apply    14_dual_nssa_translator
labs/labtool.sh 06_nssa show R1 "show ip ospf database external"
labs/labtool.sh 06_nssa rollback 14_dual_nssa_translator
```

The two scenarios both set up the NSSA and use R4's Loopback1: roll one back before applying the other.

## What you should see

These are the lines the automated verification checks; both scenarios passed apply and rollback on the shared lab.

**`06_nssa` applied** (check after 70 s). The area-1 adjacencies bounce once (the NSSA flag is in the hellos) and return to `FULL`.

```
R3# show ip route ospf                  O N2  10.4.4.0/24 [110/20] via 10.1.34.2 ...
R1# show ip route ospf                  O E2  10.4.4.0/24 [110/20] via 10.0.123.x ...
R3# show ip ospf neighbor               10.255.0.4  ...  FULL/  -  ...
```

`show ip ospf database nssa-external` on R3 shows the type-7 LSA from R4; `show ip ospf database external` on R1 shows the
type-5 LSA R3 created from it. Rollback removes the redistribution, the route-map and the area type; both routes disappear.

**`14_dual_nssa_translator` applied** (check after 70 s). The expectation from theory is two type-5 LSAs, one from each ABR.
What this lab really shows (verified on the routers) is a **takeover**: R1 has exactly one type-5 LSA for 10.4.4.0/24, and its
advertising router is R2, not R3:

```
R1# show ip ospf database external      ... Advertising Router: 10.255.0.2 ...   (and no 10.255.0.3)
```

Nothing logs an error. Every external route that enters the backbone from area 1 now depends on R2. Rollback removes the NSSA
and the forced translation from all three routers.

## Production notes

* `translate type7 always` belongs only on the ABR you deliberately want as translator. It is often copied from another design
  (for example PE-CE templates) onto routers that did not need it.
* Check who translates with `show ip ospf` on the ABRs (look for the NSSA translator state) and the *Advertising Router* of the type-5 LSA on a backbone router.
* An area cannot be stub and NSSA at the same time: roll back lab 04's `04_stub_area` first if you applied it on these routers.
* `03_inter_area` (lab 03) also uses R4's Loopback1: do not combine it with this lab's scenarios.

Learn more: dashboard **Learn** tab, topic *Stub and NSSA areas*.
