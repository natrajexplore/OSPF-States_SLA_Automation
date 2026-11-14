# Showcase kit: YouTube demo and LinkedIn post

Drafts to adapt in your own words. Everything shown runs from this repository: simulation mode on any PC, or the real EVE-NG lab.

## Before recording

1. Start the demo: `docker compose -f docker-compose.demo.yml up --build`, open `http://localhost:8082` (or `scripts\demo.ps1`,
   `http://localhost:5173`). For the real lab, use the EVE-NG deployment and open Grafana in a second tab.
2. Browser at 1920×1080, zoom 100 %, bookmarks bar hidden. The page's **Light/Dark** button sets the theme (dark reads best on video).
3. Click **Reset lab to baseline** once so every link is green.
4. Say "simulation mode" on camera when you use it: the purple **simulation** pill is visible in the header, and viewers should know
   which parts are modelled and which ran on real IOS.

## Video script (about 6 minutes)

| Time | Screen | Say |
|---|---|---|
| 0:00 | Lab tab, 3D view rotating | "This is an OSPF automation platform for Cisco IOS: 18 scenarios, each a production lesson, applied, verified and rolled back with one click." |
| 0:20 | Hover the four routers | "Four 7206VXR routers, two areas, a DR/BDR LAN and two ABRs. Green links are FULL adjacencies, read live from the routers." |
| 0:40 | Pick `01_adjacency`, **Apply** | "A hello-interval change on R4. Watch the SSH beam: the platform logs in, types the config at the right IOS prompt, saves, then verifies." |
| 1:10 | Link turns red; scroll to the transcript and Verification | "R3 and R4 drop out of FULL. The verification is a regex on `show ip ospf neighbor`, with a before/after diff." |
| 1:40 | **Rollback** | "Rollback is a template branch, not a config archive restore, and it is verified too." |
| 2:00 | Monitor tab, Live events | "Every state change is an event: neighbor lost, DR/BDR role change, config change. On the real lab they go to Kafka, Prometheus and Grafana." |
| 2:30 | Lab tab, **▶ Demo tour** | "The tour plays the main concepts back to back: DR/BDR election, NSSA with type-7 to type-5 translation, an MTU mismatch stuck in EXSTART, and OSPFv3." |
| 4:00 | Switch links to **OSPFv3** during steps 9-11 | "IPv6 on the same links. An instance-ID mismatch kills only the v3 adjacency; OSPFv2 on the same wire stays FULL." |
| 4:40 | CLI tab: `show ip route ospf`, `show ip ospf database external` on R1 | "Read-only CLI on any router, whitelisted by the backend." |
| 5:10 | Learn tab, one topic at Expert level | "A built-in course at three levels, with a quiz per level and a 3D packet flow for each topic." |
| 5:40 | README on GitHub | "It is open source under MIT. `docker compose -f docker-compose.demo.yml up` and you have it on your laptop, no EVE-NG needed." |

## YouTube

**Title:** OSPF automation on Cisco IOS: 18 scenarios, one-click apply, verify and rollback (EVE-NG + 3D dashboard)

**Description:**

```
An open-source OSPF lab automation platform for Cisco IOS (7206VXR on EVE-NG): pick a scenario, click Apply, and the platform
configures the routers over SSH, waits for OSPF to converge, verifies the result with regex assertions and shows a before/after diff,
while a 3D view and a Kafka -> Prometheus -> Grafana pipeline show every adjacency change.

Covered: adjacency states, DR/BDR election, inter-area routes, stub and NSSA areas, E2 externals, cost steering, BFD, and the
production failures behind them (MTU and network-type mismatch, area mismatch, partial stub rollout, missing `subnets`, dual NSSA
translators, reference-bandwidth mismatch, fast hellos without BFD), plus OSPFv3.

Run it without a lab: docker compose -f docker-compose.demo.yml up  (simulation mode)
Code: https://github.com/natrajexplore/OSPF-States_SLA_Automation
Sister project (BGP attributes): https://github.com/natrajexplore/BGP-Attributes-Executor-Automation_tools

Chapters
0:00 Overview  0:40 Apply a scenario  1:40 Rollback  2:00 Live events and telemetry  2:30 Demo tour
4:00 OSPFv3  4:40 CLI  5:10 Learn  5:40 Run it yourself
```

**Tags:** OSPF, Cisco, CCNP, CCIE, network automation, NetDevOps, Netmiko, EVE-NG, Python, FastAPI, React, Kafka, Prometheus, Grafana, OSPFv3, NSSA

## LinkedIn post

```
I built an open-source platform that turns OSPF theory into one-click, verified changes on Cisco IOS.

Pick a scenario, click Apply: it logs into the routers, pushes the change at the right IOS prompt, waits for OSPF to converge,
checks the result against assertions and shows the before/after diff. Rollback is verified the same way.

18 scenarios: 8 core concepts (adjacency, DR/BDR, inter-area, stub, E2, NSSA, cost steering, BFD) and the production failure behind
each one: the MTU mismatch stuck in EXSTART, the network-type mismatch, the stub flag on only one ABR, the missing `subnets`
keyword, two NSSA translators, plus OSPFv3.

What I wanted as a network lead:
- every change is a reviewed template with an explicit rollback
- every outcome is verified, not assumed
- every adjacency change is an event (Kafka -> Prometheus -> Grafana)
- engineers can learn on it: a built-in course, 3D packet flows, quizzes

No EVE-NG? One command runs it in simulation mode on a laptop, with the same scenarios and the same assertions.

Code (MIT): https://github.com/natrajexplore/OSPF-States_SLA_Automation
Demo video: <link>

#NetworkAutomation #Cisco #OSPF #NetDevOps #Python #EVENG #CCNP
```
