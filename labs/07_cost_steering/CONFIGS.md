# 07_cost_steering: all device configurations

COST, steering traffic and the reference-bandwidth trap

Everything below is generated from `inventory.yaml`, `baseline/*.cfg`, and `scenarios/` + `templates/` of this lab by
`python scripts/make-lab-configs.py`. Do not edit it by hand. The topology, the use case and the expected output are in `README.md`.

## How to use it by hand

1. Import and start the lab (`labs/labtool.sh 07_cost_steering import` and `start`, or import `07_cost_steering.zip` in the EVE web UI and start all nodes).
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

### Scenario `07_cost_steering`: COST - raising the R4-R3 link cost steers R4's traffic to R1 through R2

At baseline every link costs 10, so R4 has two equal-cost inter-area paths to R1's loopback (via R3 and via R2: ECMP). Setting `ip ospf cost 100` on R4's Ethernet1/0 leaves only the path via R2 (10.1.24.1). The IP SLA probe R4 -> R1 keeps running over the new path, and ospf_interface_cost shows the change in Grafana. Rollback restores cost 10 and both paths return. (Cost defaults come from reference-bandwidth / interface bandwidth: 100 Mb / 10 Mb Ethernet = 10.)

Push to: **R4**, in configuration mode.

**Apply**

```
interface Ethernet1/0
 ip ospf cost 100
```

**Check the result** (after about 15 s):

- `R4# show ip route 10.255.0.1` must match `10\.1\.24\.1, from`
- `R4# show ip route 10.255.0.1` must **not** match `10\.1\.34\.1, from`

**Roll back**

```
interface Ethernet1/0
 ip ospf cost 10
```

**Check the rollback** (after about 15 s):

- `R4# show ip route 10.255.0.1` must match `10\.1\.34\.1, from`
- `R4# show ip route 10.255.0.1` must match `10\.1\.24\.1, from`

### Scenario `15_reference_bandwidth_mismatch`: REFERENCE BANDWIDTH MISMATCH - R4 alone recalculates costs, silently diverging from R1/R2/R3

`auto-cost reference-bandwidth` sets the divisor OSPF uses to turn interface bandwidth into cost (cost = reference-bandwidth / interface-bandwidth). It must match on every router in the domain, but IOS does not enforce that - it only logs a local warning, and every neighbor stays Full regardless. Raising it to 10000 Mbps on R4 alone (everyone else stays at the 100 Mbps default) silently changes R4's view of every link cost without breaking a single adjacency. This is one of the most common real-world OSPF correctness bugs on networks that mix sub-Gig links with Gig/10G ones, because the 100 Mbps IOS default can't tell a 1G link from a 10G one apart until this is raised network-wide - consistently. Rollback restores the 100 Mbps default on R4.

Push to: **R4**, in configuration mode.

**Apply**

```
router ospf 1
 auto-cost reference-bandwidth 10000
```

**Check the result** (after about 15 s):

- `R4# show ip ospf` must match `Reference bandwidth unit is 10000 mbps`

**Roll back**

```
router ospf 1
 auto-cost reference-bandwidth 100
```

## Commands used by `labtool.sh capture`

```
R4# show ip route 10.255.0.1
R4# show ip ospf interface brief
R4# show ip ospf | include Reference
```
