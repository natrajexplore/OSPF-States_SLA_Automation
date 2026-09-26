# 06_nssa: all device configurations

NSSA, type 7 in the area and one translator at the edge

Everything below is generated from `inventory.yaml`, `baseline/*.cfg`, and `scenarios/` + `templates/` of this lab by
`python scripts/make-lab-configs.py`. Do not edit it by hand. The topology, the use case and the expected output are in `README.md`.

## How to use it by hand

1. Import and start the lab (`labs/labtool.sh 06_nssa import` and `start`, or import `06_nssa.zip` in the EVE web UI and start all nodes).
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

### Scenario `06_nssa`: NSSA - R4 injects an external prefix from inside area 1 (type 7 becomes type 5 at the ABR)

Area 1 is turned into an NSSA on R2, R3 and R4. R4 redistributes its Loopback1 (10.4.4.0/24) as an external route: inside the NSSA it is a type-7 LSA (`O N2` on the ABRs). R3, the ABR with the highest router-id, is elected translator and floods it into area 0 as a type-5 LSA, so R1 sees `O E2`. Run 04 (stub) rollback first: an area cannot be stub and NSSA at once. Do not run together with 03 (both use Loopback1). Rollback removes the redistribution and the area type.

Push to: **R2, R3, R4**, in configuration mode.

**Apply**

On **R2**:

```
router ospf 1
 area 1 nssa
```

On **R3**:

```
router ospf 1
 area 1 nssa
```

On **R4**:

```
route-map LO1-ONLY permit 10
 match interface Loopback1
router ospf 1
 area 1 nssa
 redistribute connected subnets route-map LO1-ONLY
```

**Check the result** (after about 70 s):

- `R3# show ip route ospf` must match `O N2\s+10\.4\.4\.0/24`
- `R1# show ip route ospf` must match `O E2\s+10\.4\.4\.0/24`
- `R3# show ip ospf neighbor` must match `10\.255\.0\.4\s+\d+\s+FULL`

**Roll back**

On **R2**:

```
router ospf 1
 no area 1 nssa
```

On **R3**:

```
router ospf 1
 no area 1 nssa
```

On **R4**:

```
router ospf 1
 no redistribute connected
 no area 1 nssa
no route-map LO1-ONLY
```

**Check the rollback** (after about 70 s):

- `R1# show ip route ospf` must **not** match `O E2\s+10\.4\.4\.0/24`
- `R3# show ip route ospf` must **not** match `O N2\s+10\.4\.4\.0/24`
- `R3# show ip ospf neighbor` must match `10\.255\.0\.4\s+\d+\s+FULL`

### Scenario `14_dual_nssa_translator`: TRANSLATOR TAKEOVER - forcing 'always' on the wrong NSSA ABR silently bypasses the elected one

Area 1 becomes NSSA on R2, R3 and R4 (like scenario 06), and R4 originates its Loopback1 as a type-7 LSA. With two ABRs (R2, R3), OSPF is supposed to elect exactly one translator - the higher router-id, R3 (10.255.0.3 > 10.255.0.2). This scenario forces `area 1 nssa translate type7 always` on R2 instead - and on this platform R2 originating the type-5 LSA is enough for R3 to never originate its own competing copy, even though R3 is the properly elected ABR. Verified live: R1 ends up with exactly one type-5 LSA for 10.4.4.0/24, advertised by R2 (10.255.0.2), never R3 (10.255.0.3). The real production risk isn't duplicate LSAs - it's a silent translator takeover: `always` on the wrong ABR (often a smaller edge device, or leftover from a PE-CE MPLS/NSSA design copied onto a router that didn't need it) quietly puts a different, unintended router in charge of every external route entering the backbone from that NSSA. Self-contained (does not require 06 to already be applied) but touches the same R4 Loopback1/route-map mechanism as 03 and 06 - roll those back first if applied. Rollback removes NSSA and the forced translation from all three routers.

Push to: **R2, R3, R4**, in configuration mode.

**Apply**

On **R2**:

```
router ospf 1
 area 1 nssa
 area 1 nssa translate type7 always
```

On **R3**:

```
router ospf 1
 area 1 nssa
```

On **R4**:

```
route-map LO1-ONLY permit 10
 match interface Loopback1
router ospf 1
 area 1 nssa
 redistribute connected subnets route-map LO1-ONLY
```

**Check the result** (after about 70 s):

- `R1# show ip ospf database external` must match `Advertising Router: 10\.255\.0\.2`
- `R1# show ip ospf database external` must **not** match `Advertising Router: 10\.255\.0\.3`

**Roll back**

On **R2**:

```
router ospf 1
 no area 1 nssa translate type7 always
 no area 1 nssa
```

On **R3**:

```
router ospf 1
 no area 1 nssa
```

On **R4**:

```
router ospf 1
 no redistribute connected
 no area 1 nssa
no route-map LO1-ONLY
```

**Check the rollback** (after about 70 s):

- `R1# show ip ospf database external` must **not** match `Advertising Router: 10\.255\.0\.2`
- `R3# show ip ospf neighbor` must match `10\.255\.0\.4\s+\d+\s+FULL`

## Commands used by `labtool.sh capture`

```
R3# show ip route ospf
R1# show ip route ospf
R1# show ip ospf database external
R3# show ip ospf database nssa-external
```
