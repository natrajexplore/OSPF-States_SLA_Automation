// The lab side of each Learn topic (ids match learnContent.js):
//   flows    packet flows for the 3D view: path (routers in order, along real links of the lab), one caption per router of the
//            path, the routers to mark as configured, and the scenario that produces it (null = the baseline)
//   params   the OSPF parameters of the topic: command, IOS default, whether both ends must agree, the value in this lab,
//            and the scenario that changes it
// Lab facts: R1 prio 1, R2 prio 50 (ABR), R3 prio 100 (ABR, DR), R4 area 1; every link cost 10 (Ethernet, 100/10), loopbacks 1.

export const LEARN_LAB = {
  fundamentals: {
    flows: [
      { label: "Baseline: forming an adjacency", scenario: null, highlight: [], path: ["R4", "R3", "R4"], captions: [
        "R4 sends a Hello every 10 s to 224.0.0.5 on e1/0: hello 10, dead 40, area 1, the area-type flags",
        "R3 checks that hello/dead, area and flags match, sees its own router ID in R4's Hello: Init, then 2-Way",
        "Database exchange: ExStart, Exchange (the MTU is checked in the DBD packets), Loading, then FULL",
      ] },
      { label: "01: hello 5 vs 10", scenario: "01_adjacency", highlight: ["R4"], path: ["R4", "R3"], captions: [
        "R4 now sends Hello 5 / Dead 20",
        "R3 expects 10 / 40: the Hello is dropped, no 2-Way, so R3-R4 never gets back to FULL (R4 still reaches area 0 via R2)",
      ] },
      { label: "09: MTU mismatch", scenario: "09_mtu_mismatch", highlight: ["R4"], path: ["R4", "R3", "R4"], captions: [
        "Hellos do not carry the MTU: R4 and R3 reach 2-Way normally",
        "R3 sends its DBD packets advertising MTU 1500",
        "R4 has ip mtu 1300 and rejects them: the adjacency is stuck in EXSTART / EXCHANGE",
      ] },
    ],
    params: [
      ["Hello interval", "ip ospf hello-interval", "10 s (broadcast, point-to-point)", "Yes", "10 s on every interface", "01 (R4 → 5 s), 16"],
      ["Dead interval", "ip ospf dead-interval", "4 × hello = 40 s", "Yes", "40 s", "01 (follows hello: 20 s), 16 (1 s)"],
      ["Area ID", "ip ospf 1 area <id>", "-", "Yes", "LAN area 0; R3-R4 and R2-R4 area 1", "11"],
      ["Area type (stub / NSSA flags)", "area 1 stub | nssa", "normal area", "Yes (Hello options)", "normal", "04, 06, 12, 14"],
      ["IP MTU", "ip mtu", "1500", "Yes (checked in DBD) unless ip ospf mtu-ignore", "1500", "09 (R4 → 1300)"],
      ["Network type", "ip ospf network", "broadcast on Ethernet", "In practice yes", "LAN broadcast; area-1 links point-to-point", "10"],
      ["Router ID", "router-id", "highest loopback, else highest interface IP", "Must be unique", "10.255.0.1 - .4", "-"],
      ["Process ID", "router ospf <n>", "-", "No (local only)", "1", "-"],
      ["Adjacency logging", "log-adjacency-changes detail", "on (without detail)", "No", "detail, every state change is logged", "-"],
    ],
  },
  dr_bdr: {
    flows: [
      { label: "Baseline: flooding via the DR", scenario: null, highlight: [], path: ["R1", "R3", "R2"], captions: [
        "R1 (DROTHER, priority 1) sends its LSA update to 224.0.0.6, AllDRouters: only the DR and BDR listen",
        "R3 (DR, priority 100) acknowledges and re-floods it to 224.0.0.5, AllSPFRouters",
        "R2 (BDR, priority 50) heard R1 too, and would take over at once if R3 failed",
      ] },
      { label: "02: new DR after re-election", scenario: "02_dr_bdr", highlight: ["R1", "R2", "R3"], path: ["R3", "R1", "R2"], captions: [
        "R3 now has priority 0: never DR or BDR, it is a DROTHER and sends to 224.0.0.6",
        "R1 (priority 255) won the election that clear ip ospf process forced, and floods for the segment",
        "R2 (priority 50) stays BDR",
      ] },
      { label: "10: network-type mismatch", scenario: "10_network_type_mismatch", highlight: ["R4"], path: ["R4", "R3"], captions: [
        "R4 treats e1/0 as broadcast: it waits for a DR/BDR election",
        "R3 treats the link as point-to-point, with no DR: the two never agree and the adjacency does not complete",
      ] },
    ],
    params: [
      ["Priority", "ip ospf priority", "1", "No", "R1 1, R2 50, R3 100", "02 (R1 255, R3 0)"],
      ["Priority 0", "ip ospf priority 0", "-", "No", "-", "02 (R3 can never be DR/BDR)"],
      ["Tie-breaker", "(router ID)", "highest router ID wins", "-", "10.255.0.x", "-"],
      ["Preemption", "-", "none: a better router does not take over", "-", "the DR only changes after re-election", "02 (clear ip ospf process)"],
      ["Wait timer", "-", "= dead interval (40 s)", "-", "40 s before the first election", "02 (settle 90 s)"],
      ["Network type", "ip ospf network broadcast | point-to-point", "broadcast on Ethernet", "Yes in practice", "LAN broadcast (DR), area-1 links p2p (no DR)", "10"],
      ["Multicast groups", "-", "224.0.0.5 all OSPF routers, 224.0.0.6 DR/BDR", "-", "-", "-"],
      ["DROTHER ↔ DROTHER", "-", "stays 2-WAY (normal)", "-", "only one DROTHER at baseline", "-"],
    ],
  },
  areas: {
    flows: [
      { label: "03: a type-3 summary", scenario: "03_inter_area", highlight: ["R4"], path: ["R4", "R3", "R1"], captions: [
        "R4 puts Loopback1 10.4.4.0/24 in area 1 (network point-to-point, so a /24, not a /32): it is in R4's type-1 router LSA",
        "R3, an ABR, turns it into a type-3 summary LSA for area 0 (R2 does the same)",
        "R1 installs O IA 10.4.4.0/24",
      ] },
      { label: "11: area mismatch", scenario: "11_area_mismatch", highlight: ["R4"], path: ["R4", "R3"], captions: [
        "R4's e1/0 now says area 0 in its Hellos",
        "R3's e1/1 is in area 1: the Hellos are discarded, no adjacency, no error on the interface",
      ] },
    ],
    params: [
      ["Interface area", "ip ospf 1 area <id>", "-", "Yes", "LAN area 0; area-1 links", "03 (R4 Lo1), 11"],
      ["ABR", "(an interface in area 0 and in another area)", "-", "-", "R2 and R3", "-"],
      ["Loopback network type", "ip ospf network point-to-point", "LOOPBACK: advertised as /32", "No", "Lo1 advertised as /24", "03"],
      ["LSA types in this lab", "-", "1 router, 2 network (DR), 3 summary, 4 ASBR summary, 5 external, 7 NSSA external", "-", "1, 2, 3 at baseline", "03, 05, 06"],
      ["Inter-area summarisation", "area 1 range <prefix> <mask>", "none", "-", "not configured", "-"],
    ],
  },
  stub_nssa: {
    flows: [
      { label: "04: stub, a default route", scenario: "04_stub_area", highlight: ["R2", "R3", "R4"], path: ["R3", "R4"], captions: [
        "R3 (ABR): area 1 is stub, so type-5 LSAs stay out and R3 originates a type-3 default 0.0.0.0/0 (R2 too)",
        "R4 installs O*IA 0.0.0.0/0 and no longer has any O E2 route",
      ] },
      { label: "12: stub on R3 only", scenario: "12_partial_stub_rollout", highlight: ["R3"], path: ["R3", "R4", "R2"], captions: [
        "R3 sets the stub flag (E-bit clear) in its area-1 Hellos",
        "R4 is still a normal area: flags differ, the R3-R4 adjacency drops",
        "R2-R4 is a separate link and stays FULL: a partial, easy-to-miss outage",
      ] },
      { label: "06: NSSA type 7 → 5", scenario: "06_nssa", highlight: ["R2", "R3", "R4"], path: ["R4", "R3", "R1"], captions: [
        "R4 redistributes Loopback1: a type-7 LSA inside the NSSA (O N2 on the ABRs)",
        "R3, the ABR with the highest router ID, translates it into a type-5 LSA for area 0",
        "R1 installs O E2 10.4.4.0/24",
      ] },
      { label: "14: translator takeover", scenario: "14_dual_nssa_translator", highlight: ["R2", "R3", "R4"], path: ["R4", "R2", "R1"], captions: [
        "R4 originates the same type-7 LSA",
        "R2 has translate type7 always: it translates, and R3, the elected translator, stands down",
        "R1's only type-5 LSA for 10.4.4.0/24 says Advertising Router 10.255.0.2",
      ] },
    ],
    params: [
      ["Stub area", "area 1 stub", "normal area", "Yes, every router of the area", "normal", "04, 12 (R3 only)"],
      ["Totally stubby", "area 1 stub no-summary (ABRs)", "-", "ABRs only", "not configured", "-"],
      ["Default cost into the stub", "area 1 default-cost", "1", "No", "1", "04"],
      ["NSSA", "area 1 nssa", "normal area", "Yes, every router of the area", "normal", "06, 14"],
      ["NSSA default route", "area 1 nssa default-information-originate", "none (unless no-summary)", "No", "not configured", "-"],
      ["Translator election", "-", "the NSSA ABR with the highest router ID", "-", "R3 (10.255.0.3)", "06"],
      ["Forced translator", "area 1 nssa translate type7 always", "off", "No", "off", "14 (on R2)"],
    ],
  },
  external_redistribution: {
    flows: [
      { label: "05: an O E2 route", scenario: "05_external_e2", highlight: ["R1"], path: ["R1", "R3", "R4"], captions: [
        "R1 becomes an ASBR: static 172.16.99.0/24 becomes a type-5 LSA, metric 20, type E2",
        "R3 floods the type 5 on unchanged and adds a type-4 LSA so area 1 can find R1",
        "R4 installs O E2 172.16.99.0/24 [110/20]: an E2 metric does not grow with distance",
      ] },
      { label: "13: missing subnets", scenario: "13_subnets_keyword", highlight: ["R1"], path: ["R1"], captions: [
        "R1: redistribute static without subnets only takes classful networks. 172.16.199.0/24 is part of 172.16.0.0/16, so no LSA is created, and nothing leaves R1",
      ] },
    ],
    params: [
      ["Redistribution", "redistribute static subnets", "subnets needed on classic IOS", "-", "none at baseline", "05, 13 (without subnets)"],
      ["External metric", "redistribute … metric <n>", "20 (1 for BGP)", "-", "20", "05"],
      ["Metric type", "metric-type 1 | 2", "2 (E2: the metric stays the same)", "-", "2", "05 (vars ext_metric_type)"],
      ["ASBR", "(any router that redistributes)", "-", "-", "R1 in 05 and 13; R4 in 06 and 14", "05, 06, 13, 14"],
      ["Filter", "redistribute … route-map <name>", "everything of that source", "-", "LO1-ONLY on R4 (06, 14)", "06, 14"],
    ],
  },
  cost_path_selection: {
    flows: [
      { label: "Baseline: path 1 of 2 (via R3)", scenario: null, highlight: [], path: ["R4", "R3", "R1"], captions: [
        "R4 → R3: cost 10 (Ethernet: 100 Mb reference / 10 Mb)",
        "R3 → R1's loopback: 10 (LAN) + 1 (loopback) = 11, advertised by R3 as a summary",
        "Total 21. The path via R2 is also 21, so both are used (equal-cost multipath)",
      ] },
      { label: "Baseline: path 2 of 2 (via R2)", scenario: null, highlight: [], path: ["R4", "R2", "R1"], captions: [
        "R4 → R2: cost 10", "R2 → R1's loopback: 11", "Total 21, equal to the path via R3",
      ] },
      { label: "07: cost 100 steers to R2", scenario: "07_cost_steering", highlight: ["R4"], path: ["R4", "R2", "R1"], captions: [
        "R4's e1/0 now costs 100: via R3 = 111",
        "Via R2 = 21: the only best path now",
        "R1 answers the IP SLA probe over the new path",
      ] },
      { label: "15: reference bandwidth", scenario: "15_reference_bandwidth_mismatch", highlight: ["R4"], path: ["R4"], captions: [
        "R4 alone uses reference 10000 Mb. Its explicit costs (10) do not move, but any automatic cost would now be 100 × what R1-R3 compute, with no alarm",
      ] },
    ],
    params: [
      ["Interface cost", "ip ospf cost", "reference / bandwidth", "No", "10 on every link", "07 (R4 e1/0 → 100)"],
      ["Reference bandwidth", "auto-cost reference-bandwidth <Mb>", "100 Mb", "Should (not checked)", "100 Mb", "15 (R4 → 10000)"],
      ["Ethernet cost", "(automatic)", "100 / 10 Mb = 10", "-", "10", "-"],
      ["Loopback cost", "(automatic)", "1", "-", "1", "-"],
      ["Equal-cost paths", "maximum-paths", "4", "No", "2 used R4 → R1", "07"],
    ],
  },
  fast_convergence: {
    flows: [
      { label: "16: fast hellos", scenario: "16_fast_hello_no_bfd", highlight: ["R3", "R4"], path: ["R3", "R4"], captions: [
        "R3 sends a Hello every 250 ms (hello-multiplier 4)",
        "R4 declares R3 dead after 1 s of silence instead of 40 s",
      ] },
      { label: "Failover after R3-R4 dies", scenario: "16_fast_hello_no_bfd", highlight: ["R3", "R4"], path: ["R4", "R2", "R1"], captions: [
        "About 1 s after R3's e1/1 goes silent, R4 removes the R3 adjacency and runs SPF",
        "The path via R2 is now the only one",
        "R1: the IP SLA probe keeps getting answers",
      ] },
    ],
    params: [
      ["Fast hellos", "ip ospf dead-interval minimal hello-multiplier <n>", "off", "Yes (dead interval)", "off", "16 (n = 4: hello 250 ms, dead 1 s)"],
      ["BFD timers", "bfd interval <ms> min_rx <ms> multiplier <n>", "off", "Negotiated", "off", "08 (500 / 500 / 3) - broken on Dynamips"],
      ["OSPF uses BFD", "ip ospf bfd", "off", "Both ends", "off", "08 - do not run here"],
      ["Default detection", "dead interval", "40 s", "Yes", "40 s", "-"],
    ],
  },
  monitoring: {
    flows: [
      { label: "IP SLA probe R4 → R1", scenario: null, highlight: ["R4"], path: ["R4", "R3", "R1", "R3", "R4"], captions: [
        "R4: ip sla 1 sends an icmp-echo from Loopback0 every 10 s",
        "Through R3 (or R2: equal cost)",
        "R1's Loopback0, 10.255.0.1, answers",
        "The reply comes back",
        "R4 records the RTT: ospf_sla_rtt_milliseconds and ospf_sla_up in Prometheus",
      ] },
    ],
    params: [
      ["IP SLA probe", "ip sla 1 / icmp-echo 10.255.0.1 source-interface Loopback0", "-", "-", "on R4, frequency 10 s", "07 and 16 move its path"],
      ["Adjacency logging", "log-adjacency-changes detail", "on (without detail)", "-", "detail on every router", "-"],
      ["Poll interval", "OSPF_POLL_INTERVAL (.env)", "20 s", "-", "20 s", "-"],
      ["Neighbor state metric", "ospf_neighbor_state", "0 Down … 7 Full", "-", "one series per adjacency", "01, 09-12"],
      ["Alert: not Full", "OSPFNeighborNotFull", "-", "-", "monitoring/prometheus/alerts.yml", "01, 09-12"],
    ],
  },
};
