# 02_dr_bdr: all device configurations

DR/BDR ELECTION, who owns the broadcast segment

Everything below is generated from `inventory.yaml`, `baseline/*.cfg`, and `scenarios/` + `templates/` of this lab by
`python scripts/make-lab-configs.py`. Do not edit it by hand. The topology, the use case and the expected output are in `README.md`.

## How to use it by hand

1. Import and start the lab (`labs/labtool.sh 02_dr_bdr import` and `start`, or import `02_dr_bdr.zip` in the EVE web UI and start all nodes).
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

### Scenario `02_dr_bdr`: DR/BDR - priority moves the designated router from R3 to R1

On the 10.0.123.0/24 broadcast segment, baseline priorities make R3 (100) the DR and R2 (50) the BDR. The scenario sets R1 to 255 and R3 to 0 (never eligible). The election is non-preemptive, so the OSPF process is cleared on all three routers to force a new election: R1 becomes DR, R2 BDR, R3 DROTHER. Rollback restores the baseline priorities and repeats the election.

Push to: **R1, R2, R3**, in configuration mode.

**Apply**

On **R1**:

```
interface Ethernet1/0
 ip ospf priority 255
```

On **R2**:

```
interface Ethernet1/0
 ip ospf priority 50
```

On **R3**:

```
interface Ethernet1/0
 ip ospf priority 0
```

Then, in exec mode on each target (answer `yes`):

```
clear ip ospf process
```

**Check the result** (after about 90 s):

- `R1# show ip ospf interface Ethernet1/0` must match `State DR,`
- `R2# show ip ospf interface Ethernet1/0` must match `State BDR,`
- `R3# show ip ospf interface Ethernet1/0` must match `State DROTHER,`

**Roll back**

On **R1**:

```
interface Ethernet1/0
 ip ospf priority 1
```

On **R2**:

```
interface Ethernet1/0
 ip ospf priority 50
```

On **R3**:

```
interface Ethernet1/0
 ip ospf priority 100
```

Then again, in exec mode on each target:

```
clear ip ospf process
```

**Check the rollback** (after about 90 s):

- `R3# show ip ospf interface Ethernet1/0` must match `State DR,`
- `R2# show ip ospf interface Ethernet1/0` must match `State BDR,`
- `R1# show ip ospf interface Ethernet1/0` must match `State DROTHER,`

### Scenario `10_network_type_mismatch`: NETWORK TYPE MISMATCH - R4 broadcast vs R3 point-to-point breaks the adjacency entirely

R4's side of the R3-R4 link is forced to `broadcast` while R3 stays `point-to-point` (the baseline for this link), and R4's OSPF process is cleared to force a fresh negotiation under the mismatch (an already-Full adjacency doesn't re-evaluate network type on its own). Network type is a local interpretation of the wire, not renegotiated between peers, so the two routers disagree about whether DR/BDR election applies here, and the adjacency never completes. A very common real incident on routed point-to-point handoffs (WAN circuits, cross-connects) where one end's config was copied from a multi-access template. Rollback restores point-to-point on R4.

Push to: **R4**, in configuration mode.

**Apply**

```
interface Ethernet1/0
 ip ospf network broadcast
```

Then, in exec mode on each target (answer `yes`):

```
clear ip ospf process
```

**Check the result** (after about 30 s):

- `R3# show ip ospf neighbor` must **not** match `10\.255\.0\.4\s+\d+\s+FULL`

**Roll back**

```
interface Ethernet1/0
 ip ospf network point-to-point
```

Then again, in exec mode on each target:

```
clear ip ospf process
```

## Commands used by `labtool.sh capture`

```
R1# show ip ospf interface Ethernet1/0
R2# show ip ospf interface Ethernet1/0
R3# show ip ospf interface Ethernet1/0
R3# show ip ospf neighbor
R4# show ip ospf interface Ethernet1/0
```
