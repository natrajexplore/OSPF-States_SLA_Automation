# 08_fast_convergence: all device configurations

FAST FAILURE DETECTION, BFD and fast hellos

Everything below is generated from `inventory.yaml`, `baseline/*.cfg`, and `scenarios/` + `templates/` of this lab by
`python scripts/make-lab-configs.py`. Do not edit it by hand. The topology, the use case and the expected output are in `README.md`.

## How to use it by hand

1. Import and start the lab (`labs/labtool.sh 08_fast_convergence import` and `start`, or import `08_fast_convergence.zip` in the EVE web UI and start all nodes).
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

### Scenario `08_bfd`: BFD - sub-second failure detection on the R3-R4 link

BFD (500 ms x 3) is enabled on the R3-R4 link and registered with OSPF. Without BFD a silent failure is found only when the 40 s dead timer expires; with BFD the adjacency is torn down in about 1.5 s. To measure it: after applying, run `shutdown` on R3 Ethernet1/1 from the console (the R4 side keeps link-up because the EVE bridge does not signal it), watch ospf_bfd_up and ospf_neighbor_state in Grafana and the IP SLA probe moving to the R2 path. Rollback removes BFD. NOTE: on this image/host, enabling BFD reliably wedges the IOS scheduler regardless of interval - tested broken at both 50 ms and 500 ms (see docs/lab.md). This is a platform defect, not something `vars` can tune around; treat this scenario as unusable here. Real hardware would not hit this.

Push to: **R3, R4**, in configuration mode.

**Apply**

On **R3**:

```
interface Ethernet1/1
 bfd interval 500 min_rx 500 multiplier 3
 ip ospf bfd
```

On **R4**:

```
interface Ethernet1/0
 bfd interval 500 min_rx 500 multiplier 3
 ip ospf bfd
```

**Check the result** (after about 30 s):

- `R4# show bfd neighbors` must match `10\.1\.34\.1\s+\d+/\d+\s+\S+\s+Up`
- `R3# show bfd neighbors` must match `10\.1\.34\.2\s+\d+/\d+\s+\S+\s+Up`
- `R3# show ip ospf neighbor` must match `10\.255\.0\.4\s+\d+\s+FULL`

**Roll back**

On **R3**:

```
interface Ethernet1/1
 no ip ospf bfd
 no bfd interval 500 min_rx 500 multiplier 3
```

On **R4**:

```
interface Ethernet1/0
 no ip ospf bfd
 no bfd interval 500 min_rx 500 multiplier 3
```

**Check the rollback** (after about 30 s):

- `R4# show bfd neighbors` must **not** match `10\.1\.34\.1\s+\d+/\d+`
- `R3# show ip ospf neighbor` must match `10\.255\.0\.4\s+\d+\s+FULL`

### Scenario `16_fast_hello_no_bfd`: FAST HELLO - sub-second OSPF timers as a BFD-free failure-detection fallback

`ip ospf dead-interval minimal hello-multiplier 4` sends 4 hellos per second and declares the neighbor down after just 1 second of silence, instead of the default 40s dead timer - no BFD required. Slower than real BFD (roughly 1s here vs BFD's tens of milliseconds) but a genuinely used, much safer production fallback when BFD isn't available on the hardware, or - as documented for scenario 08 on this lab - isn't safe to run at all (BFD wedges the IOS scheduler under Dynamips CPU contention; this scenario deliberately avoids BFD entirely). Rollback restores the 10s hello-interval baseline (40s dead timer).

Push to: **R3, R4**, in configuration mode.

**Apply**

On **R3**:

```
interface Ethernet1/1
 ip ospf dead-interval minimal hello-multiplier 4
```

On **R4**:

```
interface Ethernet1/0
 ip ospf dead-interval minimal hello-multiplier 4
```

**Check the result** (after about 30 s):

- `R3# show ip ospf interface Ethernet1/1` must match `Hello \d+ msec, Dead 1,`
- `R4# show ip ospf interface Ethernet1/0` must match `Hello \d+ msec, Dead 1,`
- `R3# show ip ospf neighbor` must match `10\.255\.0\.4\s+\d+\s+FULL`

**Roll back**

On **R3**:

```
interface Ethernet1/1
 no ip ospf dead-interval minimal hello-multiplier 4
 ip ospf hello-interval 10
```

On **R4**:

```
interface Ethernet1/0
 no ip ospf dead-interval minimal hello-multiplier 4
 ip ospf hello-interval 10
```

**Check the rollback** (after about 30 s):

- `R3# show ip ospf interface Ethernet1/1` must **not** match `Hello \d+ msec, Dead 1,`
- `R4# show ip ospf interface Ethernet1/0` must **not** match `Hello \d+ msec, Dead 1,`
- `R3# show ip ospf neighbor` must match `10\.255\.0\.4\s+\d+\s+FULL`

## Commands used by `labtool.sh capture`

```
R3# show ip ospf interface Ethernet1/1
R4# show ip ospf interface Ethernet1/0
R3# show ip ospf neighbor
```
