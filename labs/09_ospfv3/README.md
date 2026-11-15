# Lab 09: OSPFv3, IPv6 dual stack and an instance-ID mismatch

**Use case.** The network already runs OSPFv2 for IPv4 and now needs IPv6. OSPFv3 brings the same design (areas, ABRs, DR/BDR,
cost) to IPv6, as a second, independent routing protocol on the same links. This lab turns it on, shows what is different about it,
and breaks it in a way that only OSPFv3 can break.

| Scenario | What changes | What it demonstrates |
|---|---|---|
| `17_ospfv3_dual_stack` | IPv6 addresses and `ipv6 router ospf 1` on all four routers, same areas and priorities as IPv4 | Link-local neighbors and next hops, `OI` inter-area routes, Link (8) and Intra-Area-Prefix (9) LSAs, OSPFv2 untouched |
| `18_ospfv3_instance_mismatch` | R4's R3-facing interface moves to OSPFv3 instance 1 (apply 17 first) | The OSPFv3 R3-R4 adjacency disappears, OSPFv2 on the same link stays FULL, IPv6 detours via R2 |

## Topology

```
               area 0   IPv4 10.0.123.0/24   IPv6 2001:db8:123::/64   broadcast (Ethernet1/0)
     R1 (prio 1)            R2 (prio 50, ABR)        R3 (prio 100, ABR, DR)
     2001:db8:255::1        2001:db8:255::2          2001:db8:255::3
         |______________________|_________________________|
                                | 2001:db8:24::1          | 2001:db8:34::1
                     area 1 p2p | 2001:db8:24::/64        | 2001:db8:34::/64   area 1 p2p
                                | 2001:db8:24::2          | 2001:db8:34::2   <-- scenario 18 changes R4's instance ID here
                                |_________________________|
                                            R4  2001:db8:255::4 (area 1)
```

| Router | Router ID (v2 and v3) | IPv6 Loopback0 | IPv6 links | Management |
|---|---|---|---|---|
| R1 | 10.255.0.1 | 2001:db8:255::1/128 (area 0) | e1/0 2001:db8:123::1/64 (area 0, prio 1) | 192.168.99.11 |
| R2 | 10.255.0.2 | 2001:db8:255::2/128 (area 0) | e1/0 2001:db8:123::2/64 (prio 50); e1/1 2001:db8:24::1/64 (area 1, p2p) | 192.168.99.12 |
| R3 | 10.255.0.3 | 2001:db8:255::3/128 (area 0) | e1/0 2001:db8:123::3/64 (prio 100); e1/1 2001:db8:34::1/64 (area 1, p2p) | 192.168.99.13 |
| R4 | 10.255.0.4 | 2001:db8:255::4/128 (area 1) | e1/0 2001:db8:34::2/64; e1/1 2001:db8:24::2/64 (area 1, p2p) | 192.168.99.14 |

The baseline is the IPv4-only lab: scenario 17 adds all of the IPv6 configuration, and its rollback removes it. Every router's
configuration and the scenario lines per router: [`CONFIGS.md`](CONFIGS.md).

## Run it

```
labs/labtool.sh 09_ospfv3 up
labs/labtool.sh 09_ospfv3 apply    17_ospfv3_dual_stack          # about 2 minutes (the LAN's 40 s wait timer)
labs/labtool.sh 09_ospfv3 show R1 "show ipv6 route ospf"
labs/labtool.sh 09_ospfv3 apply    18_ospfv3_instance_mismatch
labs/labtool.sh 09_ospfv3 rollback 18_ospfv3_instance_mismatch
labs/labtool.sh 09_ospfv3 rollback 17_ospfv3_dual_stack
```

## What you see (captured from the shared lab on 2026-09-27)

Both scenarios passed apply and rollback on the shared lab, which has the same routers and baseline.

**`17_ospfv3_dual_stack` applied.** The same DR election as IPv4, but between OSPFv3 routers:

```
R3# show ipv6 ospf neighbor
            OSPFv3 Router with ID (10.255.0.3) (Process ID 1)
Neighbor ID     Pri   State           Dead Time   Interface ID    Interface
10.255.0.1        1   FULL/DROTHER    00:00:34    3               Ethernet1/0
10.255.0.2       50   FULL/BDR        00:00:39    3               Ethernet1/0
10.255.0.4        0   FULL/  -        00:00:32    3               Ethernet1/1
```

Next hops are link-local, and inter-area routes are `OI`. R1 reaches R4's loopback through both ABRs:

```
R1# show ipv6 route ospf
OI  2001:DB8:255::4/128 [110/20]
     via FE80::C803:E0FF:FEC7:1C, Ethernet1/0
     via FE80::C802:24FF:FE24:1C, Ethernet1/0
```

The database shows how OSPFv3 splits topology from addressing (abridged): Router and Net Link States carry no prefixes;
the prefixes are in Intra Area Prefix LSAs; each link has its own Link (Type-8) LSAs; the ABRs originate Inter Area Prefix LSAs.

```
R3# show ipv6 ospf database
		Router Link States (Area 0)          10.255.0.1, 10.255.0.2 (B), 10.255.0.3 (B)
		Net Link States (Area 0)             10.255.0.3 (the DR)
		Inter Area Prefix Link States (Area 0)
 10.255.0.2      ...  2001:DB8:255::4/128
 10.255.0.3      ...  2001:DB8:255::4/128
		Link (Type-8) Link States (Area 0)   one per router on Et1/0
		Intra Area Prefix Link States (Area 0)
```

**`18_ospfv3_instance_mismatch` applied.** R4 sends its OSPFv3 packets on Ethernet1/0 with Instance ID 1; R3 expects 0 and
discards them. R3 no longer lists `10.255.0.4 … FULL` in `show ipv6 ospf neighbor`, R4 keeps its OSPFv3 neighbor R2, and
`show ip ospf neighbor` on R3 still shows R4 FULL: OSPFv2 on the same wire is not affected.

```
R4# show ipv6 ospf interface Ethernet1/0
Ethernet1/0 is up, line protocol is up
  Link Local Address FE80::C804:E4FF:FE92:1C, Interface ID 3
  Area 1, Process ID 1, Instance ID 1, Router ID 10.255.0.4
  Network Type POINT_TO_POINT, Cost: 10
```

**Rollbacks.** 18 puts R4 back on instance 0 and the adjacency returns; 17 removes IPv6 and OSPFv3 from every router.

## Production notes

* **Set the router ID explicitly.** OSPFv3 borrows a 32-bit ID from an IPv4 address; an IPv6-only router has none, and the process does not start.
* **Dual stack means two of everything.** Timers, costs, reference bandwidth, area types and passive interfaces are configured
  separately for OSPFv2 and OSPFv3. When they drift, IPv4 and IPv6 take different paths through the same network.
* **Instance IDs must match per link.** They are used to run several OSPFv3 instances on one link (and, in the address-family model,
  to carry IPv4 over OSPFv3). A mismatch fails silently: check `show ipv6 ospf interface` on both ends.
* **Watch both protocols.** The dashboard's Lab tab can colour the 3D links by OSPFv2 or OSPFv3 adjacencies, and the CLI tab accepts
  `show ipv6 ospf …` and `show ipv6 route …`.

Learn more: dashboard **Learn** tab, topic *OSPFv3 for IPv6*.
