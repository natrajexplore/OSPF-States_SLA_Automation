# Lab 02: DR/BDR election, who owns the broadcast segment

**Use case.** On a multi-access segment OSPF elects a Designated Router (DR) and a Backup (BDR) so that routers do not all form
full adjacencies with each other. Which router wins matters: the DR generates the network LSA and relays every update on the
segment. This lab moves the DR role on purpose, and then shows the related mistake on a point-to-point link.

| Scenario | What changes | What it demonstrates |
|---|---|---|
| `02_dr_bdr` | Priority R1 255, R3 0, then `clear ip ospf process` on R1, R2, R3 | Election by priority, and that it is **not preemptive** |
| `10_network_type_mismatch` | R4's side of the R3-R4 link set to `broadcast`, R3 stays `point-to-point` | Both ends must agree on the network type |

## Topology

```
               area 0   10.0.123.0/24  broadcast segment (Ethernet1/0)   <-- the DR/BDR election happens here
     R1 (prio 1)            R2 (prio 50, ABR)        R3 (prio 100, ABR)
     10.255.0.1             10.255.0.2               10.255.0.3
         |______________________|_________________________|
                                | e1/1 10.1.24.1          | e1/1 10.1.34.1  point-to-point
                     area 1 p2p | 10.1.24.0/30            | 10.1.34.0/30    <-- scenario 10 breaks this link
                                | e1/1 10.1.24.2          | e1/0 10.1.34.2
                                |_________________________|
                                            R4  10.255.0.4 (area 1)
```

| Router | Priority on e1/0 | Router ID | Management | Baseline role on 10.0.123.0/24 |
|---|---|---|---|---|
| R1 | 1 | 10.255.0.1 | 192.168.99.11 | DROTHER |
| R2 | 50 | 10.255.0.2 | 192.168.99.12 | BDR |
| R3 | 100 | 10.255.0.3 | 192.168.99.13 | DR |
| R4 | (not on the segment) | 10.255.0.4 | 192.168.99.14 | - |

Full configurations: [`CONFIGS.md`](CONFIGS.md).

## Run it

```
labs/labtool.sh 02_dr_bdr up
labs/labtool.sh 02_dr_bdr show R1 "show ip ospf interface Ethernet1/0"
labs/labtool.sh 02_dr_bdr apply    02_dr_bdr                  # about 2 minutes: the election waits 40 s
labs/labtool.sh 02_dr_bdr rollback 02_dr_bdr
labs/labtool.sh 02_dr_bdr apply    10_network_type_mismatch
labs/labtool.sh 02_dr_bdr rollback 10_network_type_mismatch
```

## What you should see

These are the lines the automated verification checks; both scenarios passed apply and rollback on the shared lab.

**Baseline.** `show ip ospf interface Ethernet1/0` says `State DR,` on R3, `State BDR,` on R2 and `State DROTHER,` on R1.

**`02_dr_bdr` applied** (check after 90 s). Changing a priority alone does nothing: the current DR keeps its role until the
election runs again. The scenario therefore clears the OSPF process on the three routers. After the wait timer (40 s, the dead
interval) R1 reports `State DR,`, R2 `State BDR,` and R3 `State DROTHER,`. Priority 0 means R3 can never be elected.
Rollback restores 1 / 50 / 100 and repeats the election, so R3 is DR again.

**`10_network_type_mismatch` applied** (check after 30 s). R4 now expects a DR/BDR election on a link where R3 does not run one.
Hellos are exchanged, but the adjacency never completes: R3 no longer lists `10.255.0.4 ... FULL`. R4 still reaches the backbone
through R2. Rollback restores `ip ospf network point-to-point` on R4.

## Production notes

* **Non-preemption is a feature.** Re-electing a DR floods the segment, so OSPF keeps the current DR. To move it in a
  maintenance window, change priorities and then reset the adjacencies (clear the process, or bounce the interfaces), as this scenario does.
* **Priority 0** on routers that should never be DR (for example small branch routers on a shared hub segment) is the common design.
* **Network type mismatch** usually comes from copying an interface template from an Ethernet LAN onto a routed point-to-point
  circuit. `show ip ospf interface` shows `Network Type POINT_TO_POINT` versus `BROADCAST`; compare both ends.
* Grafana: `ospf_interface_role` changes and the role-change counter rises when the DR moves.

Learn more: dashboard **Learn** tab, topic *DR/BDR election*.
