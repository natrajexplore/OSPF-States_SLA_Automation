# Lab 05: External routes, an ASBR and the `subnets` trap

**Use case.** A route that OSPF did not learn itself (a static route, a connected network, another protocol) enters the domain
through **redistribution** on an Autonomous System Boundary Router (ASBR). R1 plays that role here. The same command, with one
keyword missing, silently does nothing.

| Scenario | What changes | What it demonstrates |
|---|---|---|
| `05_external_e2` | R1 redistributes static 172.16.99.0/24 with `subnets`, metric-type 2 | R1 becomes an ASBR; a type-5 LSA; R3 and R4 install `O E2` with a constant metric |
| `13_subnets_keyword` | R1 redistributes static 172.16.199.0/24 **without** `subnets` | The command is accepted, nothing is logged, and the route never appears |

## Topology

```
     172.16.99.0/24 / 172.16.199.0/24  (static routes to Null0, redistributed)
                 |
     R1 (ASBR)              R2 (ABR)                 R3 (ABR)          area 0  10.0.123.0/24
     10.255.0.1             10.255.0.2               10.255.0.3
         |__________________|________________________|
                            | 10.1.24.0/30           | 10.1.34.0/30   area 1
                            |________________________|
                                        R4  10.255.0.4 (area 1, sees O E2)
```

| Router | Role | Router ID | Management |
|---|---|---|---|
| R1 | backbone, ASBR in this lab | 10.255.0.1 | 192.168.99.11 |
| R2 | ABR | 10.255.0.2 | 192.168.99.12 |
| R3 | ABR | 10.255.0.3 | 192.168.99.13 |
| R4 | internal, area 1 | 10.255.0.4 | 192.168.99.14 |

Full configurations: [`CONFIGS.md`](CONFIGS.md).

## Run it

```
labs/labtool.sh 05_external_routes up
labs/labtool.sh 05_external_routes apply    05_external_e2
labs/labtool.sh 05_external_routes show R4 "show ip route ospf"
labs/labtool.sh 05_external_routes rollback 05_external_e2
labs/labtool.sh 05_external_routes apply    13_subnets_keyword
labs/labtool.sh 05_external_routes rollback 13_subnets_keyword
```

Only one of the two can be applied at a time: both configure `redistribute static` on R1. Roll one back before applying the other.

## What you should see

These are the lines the automated verification checks; both scenarios passed apply and rollback on the shared lab.

**`05_external_e2` applied** (check after 30 s). R1 floods a type-5 LSA; the ABRs also generate a type-4 (ASBR summary) so that
area 1 can find R1:

```
R3# show ip ospf database external     ... Link State ID: 172.16.99.0 (External Network Number) ...
R3# show ip route ospf                 O E2  172.16.99.0/24 [110/20] via 10.0.123.1 ...
R4# show ip route ospf                 O E2  172.16.99.0/24 [110/20] via ...
```

The metric is 20 on every router: an E2 metric does not grow with distance. To see the difference, set `ext_metric_type: 1` in
`scenarios/05_external_e2.yaml`; R4 then shows `O E1` with the external metric **plus** the internal cost to R1.

**`13_subnets_keyword` applied** (check after 20 s). Without `subnets`, IOS redistributes only classful networks.
172.16.199.0/24 is a subnet of the class B network 172.16.0.0/16, so it is skipped. The verification checks that `172.16.199.0`
is **absent** from R3's routing table, after apply and after rollback; rollback also checks that `redistribute static` is gone from R1.

## Production notes

* Always write `redistribute ... subnets` on classic IOS (newer IOS XE releases add it automatically, which is why configs copied
  between platforms break). Verify redistribution with `show ip ospf database external` on the ASBR, not only on a far router.
* **E2 or E1?** E2 (the default) is right when there is a single exit to the external network. With two ASBRs for the same prefix,
  E1 lets each router pick the closer one.
* Filter what you redistribute with a route-map; redistributing everything is how internal prefixes leak.

Learn more: dashboard **Learn** tab, topic *External routes and redistribution*.
