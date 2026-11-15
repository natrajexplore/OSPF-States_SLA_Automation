# 09_ospfv3: all device configurations

OSPFv3, IPv6 dual stack beside OSPFv2 and an instance-ID mismatch

Everything below is generated from `inventory.yaml`, `baseline/*.cfg`, and `scenarios/` + `templates/` of this lab by
`python scripts/make-lab-configs.py`. Do not edit it by hand. The topology, the use case and the expected output are in `README.md`.

## How to use it by hand

1. Import and start the lab (`labs/labtool.sh 09_ospfv3 import` and `start`, or import `09_ospfv3.zip` in the EVE web UI and start all nodes).
2. Open each router's console. A fresh router asks `Would you like to enter the initial configuration dialog? [yes/no]:`. Answer `no`, press Enter, then type `enable`.
3. Type `configure terminal` and paste that router's block below, then `end` and `write memory`.
4. Routers can be pasted in any order. Adjacencies come up as soon as both ends of a link are configured (about 40 s on the broadcast segment, the OSPF wait timer).

**Management lines.** Every block contains a small management section (`ip vrf MGMT`, `FastEthernet0/0` in that VRF, `ip route vrf MGMT`, `username lab`, `enable secret`, `line vty`). It lets the dashboard and `labtool.sh` log in over SSH and is not part of the OSPF design. For a hand-built lab you can leave it out and use only the console. To use SSH you also need `crypto key generate rsa modulus 1024` once per router (`scripts/bootstrap.py` does that).

**`no ...` lines in the baselines.** The baselines are also used to *reset* a router, so they contain `no` lines (for example `no area 1 stub`) that remove whatever a scenario may have left. On a blank router they are harmless.

## Links

| Segment | Members | Note |
|---|---|---|
| AREA0-LAN | R1 e1/0, R2 e1/0, R3 e1/0 | 10.0.123.0/24, area 0, broadcast |
| R3--R4 | R3 e1/1, R4 e1/0 | 10.1.34.0/30, area 1, point-to-point |
| R2--R4 | R2 e1/1, R4 e1/1 | 10.1.24.0/30, area 1, point-to-point (second ABR path) |

## Devices

| Router | Role | Router ID | Management IP |
|---|---|---|---|
| R1 | backbone | 10.255.0.1 | 192.168.99.11 |
| R2 | abr | 10.255.0.2 | 192.168.99.12 |
| R3 | abr | 10.255.0.3 | 192.168.99.13 |
| R4 | internal-area1 | 10.255.0.4 | 192.168.99.14 |

## R1

```
hostname R1
no ip domain lookup
ip domain name lab.local
!
ip vrf MGMT
 rd 65000:99
!
enable secret lab123
username lab privilege 15 secret lab123
!
interface Loopback0
 ip address 10.255.0.1 255.255.255.255
 ip ospf 1 area 0
!
interface FastEthernet0/0
 description === MGMT (Cloud1) ===
 ip vrf forwarding MGMT
 ip address 192.168.99.11 255.255.255.0
 duplex auto
 speed auto
 no shutdown
!
interface Ethernet1/0
 description === area 0 LAN (R1,R2,R3) ===
 ip address 10.0.123.1 255.255.255.0
 ip ospf 1 area 0
 ip ospf network broadcast
 ip ospf priority 1
 ip ospf hello-interval 10
 no shutdown
!
no ip route 172.16.99.0 255.255.255.0 Null0
router ospf 1
 router-id 10.255.0.1
 log-adjacency-changes detail
 no redistribute static
!
ip route vrf MGMT 0.0.0.0 0.0.0.0 192.168.99.1
!
line vty 0 4
 login local
 transport input ssh
!
end
```

## R2

```
hostname R2
no ip domain lookup
ip domain name lab.local
!
ip vrf MGMT
 rd 65000:99
!
enable secret lab123
username lab privilege 15 secret lab123
!
interface Loopback0
 ip address 10.255.0.2 255.255.255.255
 ip ospf 1 area 0
!
interface FastEthernet0/0
 description === MGMT (Cloud1) ===
 ip vrf forwarding MGMT
 ip address 192.168.99.12 255.255.255.0
 duplex auto
 speed auto
 no shutdown
!
interface Ethernet1/0
 description === area 0 LAN (R1,R2,R3) ===
 ip address 10.0.123.2 255.255.255.0
 ip ospf 1 area 0
 ip ospf network broadcast
 ip ospf priority 50
 ip ospf hello-interval 10
 no shutdown
!
interface Ethernet1/1
 description === area 1 to R4 ===
 ip address 10.1.24.1 255.255.255.252
 ip ospf 1 area 1
 ip ospf network point-to-point
 ip ospf hello-interval 10
 ip ospf cost 10
 no ip ospf bfd
 no shutdown
!
router ospf 1
 router-id 10.255.0.2
 log-adjacency-changes detail
 no area 1 stub
 no area 1 nssa
!
ip route vrf MGMT 0.0.0.0 0.0.0.0 192.168.99.1
!
line vty 0 4
 login local
 transport input ssh
!
end
```

## R3

```
hostname R3
no ip domain lookup
ip domain name lab.local
!
ip vrf MGMT
 rd 65000:99
!
enable secret lab123
username lab privilege 15 secret lab123
!
interface Loopback0
 ip address 10.255.0.3 255.255.255.255
 ip ospf 1 area 0
!
interface FastEthernet0/0
 description === MGMT (Cloud1) ===
 ip vrf forwarding MGMT
 ip address 192.168.99.13 255.255.255.0
 duplex auto
 speed auto
 no shutdown
!
interface Ethernet1/0
 description === area 0 LAN (R1,R2,R3) ===
 ip address 10.0.123.3 255.255.255.0
 ip ospf 1 area 0
 ip ospf network broadcast
 ip ospf priority 100
 ip ospf hello-interval 10
 no shutdown
!
interface Ethernet1/1
 description === area 1 to R4 ===
 ip address 10.1.34.1 255.255.255.252
 ip ospf 1 area 1
 ip ospf network point-to-point
 ip ospf hello-interval 10
 ip ospf cost 10
 no ip ospf bfd
 no shutdown
!
router ospf 1
 router-id 10.255.0.3
 log-adjacency-changes detail
 no area 1 stub
 no area 1 nssa
!
ip route vrf MGMT 0.0.0.0 0.0.0.0 192.168.99.1
!
line vty 0 4
 login local
 transport input ssh
!
end
```

## R4

```
hostname R4
no ip domain lookup
ip domain name lab.local
!
ip vrf MGMT
 rd 65000:99
!
enable secret lab123
username lab privilege 15 secret lab123
!
interface Loopback0
 ip address 10.255.0.4 255.255.255.255
 ip ospf 1 area 1
!
interface FastEthernet0/0
 description === MGMT (Cloud1) ===
 ip vrf forwarding MGMT
 ip address 192.168.99.14 255.255.255.0
 duplex auto
 speed auto
 no shutdown
!
interface Loopback1
 description === stub prefix, advertised by scenario 03 ===
 ip address 10.4.4.1 255.255.255.0
 no ip ospf 1 area 1
 no ip ospf network
!
interface Ethernet1/0
 description === area 1 to R3 ===
 ip address 10.1.34.2 255.255.255.252
 ip ospf 1 area 1
 ip ospf network point-to-point
 ip ospf hello-interval 10
 ip ospf cost 10
 no ip ospf bfd
 no shutdown
!
interface Ethernet1/1
 description === area 1 to R2 ===
 ip address 10.1.24.2 255.255.255.252
 ip ospf 1 area 1
 ip ospf network point-to-point
 ip ospf hello-interval 10
 ip ospf cost 10
 no ip ospf bfd
 no shutdown
!
router ospf 1
 router-id 10.255.0.4
 log-adjacency-changes detail
 no area 1 stub
 no area 1 nssa
 no redistribute connected
!
ip sla 1
 icmp-echo 10.255.0.1 source-interface Loopback0
 frequency 10
ip sla schedule 1 life forever start-time now
!
ip route vrf MGMT 0.0.0.0 0.0.0.0 192.168.99.1
!
line vty 0 4
 login local
 transport input ssh
!
end
```

## Scenarios (the change the lab is about)

### Scenario `17_ospfv3_dual_stack`: OSPFv3 - IPv6 dual stack: the same areas, DR/BDR and ABRs, running beside OSPFv2

Adds IPv6 to every router and runs OSPFv3 (classic `ipv6 router ospf 1`) beside the existing OSPFv2, with the same design: the 2001:db8:123::/64 LAN in area 0 (same priorities, so R3 is DR again), the two R4 links in area 1 as point-to-point, and a /128 IPv6 loopback per router. OSPFv3 runs per link, not per subnet: neighbors talk from their fe80:: link-local addresses, the router ID is still a 32-bit number (10.255.0.x), and inter-area routes appear as `OI`. R1 learns R4's loopback 2001:db8:255::4/128 as `OI`, carried by a type-3 inter-area-prefix LSA from the ABRs. IPv4 OSPF is untouched. Rollback removes IPv6 and OSPFv3 from all four routers. Apply this before scenario 18.

Push to: **R1, R2, R3, R4**, in configuration mode.

**Apply**

On **R1**:

```
ipv6 unicast-routing
ipv6 router ospf 1
 router-id 10.255.0.1
 log-adjacency-changes detail
interface Loopback0
 ipv6 address 2001:db8:255::1/128
 ipv6 ospf 1 area 0
interface Ethernet1/0
 ipv6 address 2001:db8:123::1/64
 ipv6 ospf priority 1
 ipv6 ospf 1 area 0
```

On **R2**:

```
ipv6 unicast-routing
ipv6 router ospf 1
 router-id 10.255.0.2
 log-adjacency-changes detail
interface Loopback0
 ipv6 address 2001:db8:255::2/128
 ipv6 ospf 1 area 0
interface Ethernet1/0
 ipv6 address 2001:db8:123::2/64
 ipv6 ospf priority 50
 ipv6 ospf 1 area 0
interface Ethernet1/1
 ipv6 address 2001:db8:24::1/64
 ipv6 ospf network point-to-point
 ipv6 ospf 1 area 1
```

On **R3**:

```
ipv6 unicast-routing
ipv6 router ospf 1
 router-id 10.255.0.3
 log-adjacency-changes detail
interface Loopback0
 ipv6 address 2001:db8:255::3/128
 ipv6 ospf 1 area 0
interface Ethernet1/0
 ipv6 address 2001:db8:123::3/64
 ipv6 ospf priority 100
 ipv6 ospf 1 area 0
interface Ethernet1/1
 ipv6 address 2001:db8:34::1/64
 ipv6 ospf network point-to-point
 ipv6 ospf 1 area 1
```

On **R4**:

```
ipv6 unicast-routing
ipv6 router ospf 1
 router-id 10.255.0.4
 log-adjacency-changes detail
interface Loopback0
 ipv6 address 2001:db8:255::4/128
 ipv6 ospf 1 area 1
interface Ethernet1/0
 ipv6 address 2001:db8:34::2/64
 ipv6 ospf network point-to-point
 ipv6 ospf 1 area 1
interface Ethernet1/1
 ipv6 address 2001:db8:24::2/64
 ipv6 ospf network point-to-point
 ipv6 ospf 1 area 1
```

**Check the result** (after about 75 s):

- `R3# show ipv6 ospf neighbor` must match `10\.255\.0\.4\s+\d+\s+FULL`
- `R3# show ipv6 ospf neighbor` must match `10\.255\.0\.1\s+\d+\s+FULL`
- `R1# show ipv6 route ospf` must match `(?i)OI\s+2001:DB8:255::4/128`
- `R4# show ipv6 route ospf` must match `(?i)OI\s+2001:DB8:123::/64`
- `R3# show ip ospf neighbor` must match `10\.255\.0\.4\s+\d+\s+FULL`

**Roll back**

On **R1**:

```
interface Loopback0
 no ipv6 ospf 1 area 0
 no ipv6 address
interface Ethernet1/0
 no ipv6 ospf 1 area 0
 no ipv6 ospf priority
 no ipv6 address
no ipv6 router ospf 1
no ipv6 unicast-routing
```

On **R2**:

```
interface Loopback0
 no ipv6 ospf 1 area 0
 no ipv6 address
interface Ethernet1/0
 no ipv6 ospf 1 area 0
 no ipv6 ospf priority
 no ipv6 address
interface Ethernet1/1
 no ipv6 ospf 1 area 1
 no ipv6 ospf network point-to-point
 no ipv6 address
no ipv6 router ospf 1
no ipv6 unicast-routing
```

On **R3**:

```
interface Loopback0
 no ipv6 ospf 1 area 0
 no ipv6 address
interface Ethernet1/0
 no ipv6 ospf 1 area 0
 no ipv6 ospf priority
 no ipv6 address
interface Ethernet1/1
 no ipv6 ospf 1 area 1
 no ipv6 ospf network point-to-point
 no ipv6 address
no ipv6 router ospf 1
no ipv6 unicast-routing
```

On **R4**:

```
interface Loopback0
 no ipv6 ospf 1 area 1
 no ipv6 address
interface Ethernet1/0
 no ipv6 ospf 1 area 1
 no ipv6 ospf network point-to-point
 no ipv6 address
interface Ethernet1/1
 no ipv6 ospf 1 area 1
 no ipv6 ospf network point-to-point
 no ipv6 address
no ipv6 router ospf 1
no ipv6 unicast-routing
```

**Check the rollback** (after about 75 s):

- `R3# show ipv6 ospf neighbor` must **not** match `FULL`
- `R1# show ipv6 route ospf` must **not** match `(?i)2001:DB8:255::4`
- `R3# show ip ospf neighbor` must match `10\.255\.0\.4\s+\d+\s+FULL`

### Scenario `18_ospfv3_instance_mismatch`: OSPFv3 INSTANCE ID MISMATCH - R4 uses instance 1 on the R3 link: the v3 adjacency drops, OSPFv2 stays Full

Needs scenario 17 applied first. OSPFv3 carries an Instance ID in every packet header (0 by default), so several OSPFv3 instances can share one link; a router only accepts packets whose Instance ID matches its own on that interface. R4 moves its R3-facing interface to instance 1 while R3 stays on 0: each side silently discards the other's Hellos and the R3-R4 OSPFv3 adjacency disappears, with no error on the interface. OSPFv2 on the very same link is a separate protocol and stays FULL, so IPv4 works while IPv6 quietly takes the path through R2. A real incident pattern when instance IDs are used to separate address families or tenants and one end is configured differently. Rollback puts R4 back on instance 0.

Push to: **R4**, in configuration mode.

**Apply**

```
interface Ethernet1/0
 no ipv6 ospf 1 area 1
 ipv6 ospf 1 area 1 instance 1
```

**Check the result** (after about 50 s):

- `R3# show ipv6 ospf neighbor` must **not** match `10\.255\.0\.4\s+\d+\s+FULL`
- `R4# show ipv6 ospf neighbor` must match `10\.255\.0\.2\s+\d+\s+FULL`
- `R3# show ip ospf neighbor` must match `10\.255\.0\.4\s+\d+\s+FULL`

**Roll back**

```
interface Ethernet1/0
 no ipv6 ospf 1 area 1 instance 1
 ipv6 ospf 1 area 1
```

**Check the rollback** (after about 50 s):

- `R3# show ipv6 ospf neighbor` must match `10\.255\.0\.4\s+\d+\s+FULL`
- `R3# show ip ospf neighbor` must match `10\.255\.0\.4\s+\d+\s+FULL`

## Commands used by `labtool.sh capture`

```
R3# show ipv6 ospf neighbor
R4# show ipv6 ospf neighbor
R1# show ipv6 route ospf
R3# show ip ospf neighbor
R4# show ipv6 ospf interface Ethernet1/0
```
