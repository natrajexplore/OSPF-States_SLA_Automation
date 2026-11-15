# Lab 08: Fast failure detection, BFD and fast hellos

**Use case.** With default timers OSPF notices a silent failure (the link stays up but the neighbor stops answering, for example
across a switch or a provider circuit) only when the 40-second dead interval expires. Two ways to shorten that are compared here.

| Scenario | What changes | Status on this platform |
|---|---|---|
| `08_bfd` | BFD 500 ms x 3 on the R3-R4 link, registered with OSPF (`ip ospf bfd`) | **Do not run.** It wedges the emulated router (see below) |
| `16_fast_hello_no_bfd` | `ip ospf dead-interval minimal hello-multiplier 4` on R3 and R4 | Works: 4 hellos per second, neighbor declared down after 1 s |

## Topology

```
               area 0   10.0.123.0/24  broadcast segment (Ethernet1/0)
     R1                     R2 (ABR)                 R3 (ABR)
     10.255.0.1             10.255.0.2               10.255.0.3
         |__________________|________________________| e1/1 10.1.34.1
                            | 10.1.24.0/30           | 10.1.34.0/30   <-- fast detection on this link
                            |________________________| e1/0 10.1.34.2
                                        R4  10.255.0.4
```

| Router | Role | Router ID | Management | Interface in this lab |
|---|---|---|---|---|
| R3 | ABR | 10.255.0.3 | 192.168.99.13 | Ethernet1/1 |
| R4 | area 1 | 10.255.0.4 | 192.168.99.14 | Ethernet1/0 |

R1 and R2 (192.168.99.11, .12) are unchanged. Full configurations: [`CONFIGS.md`](CONFIGS.md).

## Run it

```
labs/labtool.sh 08_fast_convergence up
labs/labtool.sh 08_fast_convergence apply    16_fast_hello_no_bfd
labs/labtool.sh 08_fast_convergence show R3 "show ip ospf interface Ethernet1/1"
labs/labtool.sh 08_fast_convergence rollback 16_fast_hello_no_bfd
```

## What you should see

**`16_fast_hello_no_bfd` applied** (check after 30 s; passed apply and rollback on the shared lab). Both ends report sub-second hellos and a one-second dead interval, and the adjacency stays `FULL`:

```
R3# show ip ospf interface Ethernet1/1   ... Timer intervals configured, Hello 250 msec, Dead 1, ...
R4# show ip ospf interface Ethernet1/0   ... Hello 250 msec, Dead 1, ...
R3# show ip ospf neighbor                10.255.0.4  ...  FULL/  -  ...
```

To see the effect, `shutdown` R3's Ethernet1/1 from its console while watching R4 (`show ip ospf neighbor`, or the neighbor state
timeline in Grafana): R4 drops the adjacency after about one second instead of 40, and its IP SLA probe moves to the R2 path.
Rollback removes the fast timers and restores `hello-interval 10`.

## Why `08_bfd` must not be run here

Enabling BFD on `c7200-adventerprisek9-mz.152-4.S6` under Dynamips reliably wedges the IOS scheduler within seconds, at 50 ms and
at 500 ms intervals alike: `%SCHED-5-INT_DISABLED_BEFORE_PREEMPTION` at the same internal address, then the router stops answering
SSH, ping and console. It is a defect of the emulated platform, not of the configuration; real hardware does not do this. The
scenario is kept so the configuration and its checks can be read and used on real equipment. The recovery procedure, if you run it
by mistake, is in [`docs/lab.md`](../../docs/lab.md#first-run-checklist) (stop the wedged node, shut the healthy peer's interface
before restarting it, and re-run `bootstrap` and `baseline` if the router comes back unconfigured).

## Production notes

* **BFD** is the right tool where the platform supports it: tens of milliseconds, cheap, shared by OSPF, BGP and static routes.
* **Fast hellos** are the fallback: about one second, but every hello is processed by the routing CPU, four per second per
  neighbor. Use them on a handful of critical links, not everywhere.
* Timers must match on both ends: fast hellos on one side only is the timer mismatch of lab 01.

Learn more: dashboard **Learn** tab, topic *Fast convergence*.
