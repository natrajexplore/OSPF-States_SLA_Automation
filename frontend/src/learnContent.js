// Static OSPF reference content, 3 depth levels per topic. Each level is a list of blocks:
// a plain string is a paragraph, {h: "..."} a subheading, {ul: [...]} a bullet list, {code: "..."} a code block.
// `scenarios` cross-links to backend/scenarios/*.yaml ids shown on the Scenarios tab.

export const TOPICS = [
  {
    id: "fundamentals",
    title: "OSPF Fundamentals & Neighbor States",
    blurb: "What OSPF actually is, and the state machine every adjacency goes through.",
    scenarios: ["01_adjacency", "09_mtu_mismatch"],
    beginner: [
      "OSPF (Open Shortest Path First) is a routing protocol that lets routers automatically learn the network's " +
        "topology and calculate the best path to every destination. Instead of you typing in routes by hand, each " +
        "router builds a full map of the network and works out the shortest path itself.",
      "Routers that speak OSPF to each other over a link become “neighbors,” and once they agree to " +
        "exchange full routing information, they're called an “adjacency.” Getting from strangers to a full " +
        "adjacency is a step-by-step process - if you've ever seen a neighbor “stuck” and never reaching " +
        "Full, something interrupted one of these steps.",
      { h: "The neighbor states, in order" },
      { ul: [
        "Down - nothing heard from this neighbor yet.",
        "Init - a Hello was received, but it doesn't list us yet, so it's not mutual.",
        "2-Way - Hellos are mutual; on a shared segment, DR/BDR election happens here.",
        "ExStart - the two routers negotiate who leads the database exchange (the higher Router ID wins).",
        "Exchange - each side describes its whole link-state database to the other (DBD packets).",
        "Loading - any pieces missing from that description get requested and filled in.",
        "Full - fully synchronized. This is the adjacency you want to see.",
      ] },
      "You can see this live: apply scenario 01 (Adjacency states) and watch R3's neighbor table on the Monitor tab " +
        "as R4 drops out of Full, or scenario 09 (MTU mismatch) to see a neighbor get stuck partway through instead " +
        "of never starting at all - two different-looking symptoms with completely different causes.",
    ],
    pro: [
      "OSPF is a link-state protocol: every router floods small pieces of topology information (Link-State " +
        "Advertisements, LSAs) to every other router in the area, and each router independently runs Dijkstra's " +
        "Shortest Path First algorithm over the resulting database to compute its own routing table. This is " +
        "fundamentally different from distance-vector protocols (RIP, EIGRP) where routers just tell each other " +
        "“here's my distance to X” without sharing the full topology.",
      "Hello packets (multicast to 224.0.0.5) carry the parameters that must match for two routers to become " +
        "neighbors at all: the hello-interval and dead-interval, the area ID, the subnet mask (on broadcast/NBMA), " +
        "authentication settings, and the stub-area flags. Any mismatch there and the Hello is silently discarded - " +
        "no adjacency, no log message on the interface itself. `debug ip ospf hello` is the fastest way to see why " +
        "a neighbor never even reaches Init.",
      "Once in 2-Way, ExStart negotiates a master/slave relationship (purely for sequencing DBD packets) and an " +
        "initial DD sequence number, based on Router ID - not priority, not who sent the first Hello. Exchange then " +
        "trades DBD packets summarizing each LSA (type, ID, advertising router, sequence number, checksum, age) - " +
        "and this is where MTU matters: if a DBD would need to be fragmented because it exceeds the smaller side's " +
        "IP MTU, that side rejects it and the neighbor sits in ExStart or Exchange indefinitely (scenario 09). Note " +
        "this is only checked *during* the exchange - it doesn't tear down an adjacency that's already Full, which " +
        "is why an MTU change alone doesn't visibly break anything until the next time that adjacency resets.",
      { h: "Reading the timers" },
      "`show ip ospf neighbor` shows state and the countdown to the dead timer. `show ip ospf interface` shows the " +
        "configured Hello/Dead/Wait/Retransmit intervals for that interface - always check both ends when an " +
        "adjacency won't form; a mismatch there is rejected in the Hello itself, before any state machine progress " +
        "happens at all.",
    ],
    expert: [
      "The state machine is formally defined per-neighbor-per-interface in RFC 2328 §10. A few of the less " +
        "obvious rules: on NBMA/point-to-multipoint networks, ExStart is reached only after eligible neighbors are " +
        "discovered (no multicast Hello discovery the way broadcast networks get it), which is why NBMA OSPF " +
        "designs are unusually sensitive to explicit `neighbor` statements and polling intervals.",
      "The DD (Database Description) sequence number, once fixed at ExStart by whoever won master/slave, is what " +
        "protects Exchange from duplicate or out-of-order DBDs - the slave echoes the master's sequence number, " +
        "the master increments and sends the next one, and receiving an unexpected DD sequence number is treated " +
        "as a protocol error that resets the adjacency back to ExStart (visible as neighbor flapping through " +
        "ExStart repeatedly without ever completing, distinct from a full Down/Init reset).",
      "MTU handling: RFC 2328 says a router SHOULD reject a DBD advertising a larger interface MTU than its own, " +
        "unless `ip ospf mtu-ignore` is set (which disables the check entirely on that interface - useful, and " +
        "occasionally necessary, on tunnel interfaces or providers with nonstandard MTUs, but it means a genuine " +
        "MTU mismatch that would fragment real traffic is no longer caught at the control-plane level - LSAs still " +
        "flow, but transit data can black-hole on oversized packets with DF set).",
      "LSA flooding is scoped: type-1 (router) and type-2 (network) LSAs flood only within an area; type-3 " +
        "(summary) cross area boundaries via ABRs; type-5 (external) flood autonomous-system-wide except into " +
        "stub/NSSA areas; type-7 (NSSA external) are area-1-scoped and get translated to type-5 at the NSSA's ABR. " +
        "Every LSA has a 32-bit sequence number (starting at 0x80000001) and a checksum, and an LSA reaching " +
        "MaxAge (3600s) without refresh is flushed - the mechanism scenario 03's rollback depends on when the " +
        "summary LSA for a withdrawn route ages out of the database, which can lag slightly behind the route " +
        "disappearing from the RIB since SPF recomputation and LSA flushing are separate processes.",
    ],
  },
  {
    id: "dr_bdr",
    title: "DR/BDR Election",
    blurb: "Why multi-access segments need a Designated Router, and how the election actually behaves.",
    scenarios: ["02_dr_bdr", "10_network_type_mismatch"],
    beginner: [
      "On a shared Ethernet segment with 3+ routers, if every router formed a full adjacency with every other " +
        "router, the number of adjacencies (and the amount of routing chatter) would grow very fast as routers are " +
        "added. OSPF avoids that by electing one router as the Designated Router (DR) and a backup (BDR); every " +
        "other router only forms a full adjacency with the DR and BDR, not with each other.",
      "The DR is chosen by OSPF priority (higher wins; priority 0 means “never eligible”), with Router ID " +
        "as the tiebreaker. In this lab's baseline, R3 (priority 100) is DR and R2 (priority 50) is BDR on the " +
        "R1-R2-R3 segment; R1 (priority 1) is neither.",
      "The important, slightly surprising part: once a DR is elected, it stays DR even if a higher-priority router " +
        "joins later - the election is non-preemptive. That's why scenario 02 needs an extra step (`clear ip ospf " +
        "process`) to force a fresh election after changing priorities; just changing the priority alone doesn't " +
        "move the DR role on its own.",
    ],
    pro: [
      "Point-to-point links don't need DR/BDR at all - there are only ever two routers on the segment, so full " +
        "adjacencies between them cost nothing extra. `ip ospf network point-to-point` tells OSPF to skip DR " +
        "election entirely on an Ethernet link wired point-to-point (a routed handoff, a cross-connect). Getting " +
        "this network-type setting wrong on just one end - broadcast on one side, point-to-point on the other - " +
        "breaks the adjacency outright (scenario 10), because the two sides now disagree about whether an election " +
        "should even happen.",
      "`show ip ospf interface <if>` shows the current DR and BDR (by Router ID and interface address), the local " +
        "router's own state (DR / BDR / DROTHER), and priority. `show ip ospf neighbor` shows each neighbor's role " +
        "from the local router's point of view.",
      "Forcing a new election: `clear ip ospf process` resets every OSPF adjacency on the router (disruptive - " +
        "everything goes through the full state machine again), which is the bluntest way to force re-election. " +
        "Less disruptive in production: bring the current DR's interface administratively down and back up, or " +
        "just wait for the DR to actually fail - either way, only the DR's own departure (or an admin-forced " +
        "reset) triggers a new election; changing everyone else's priority does not.",
    ],
    expert: [
      "The DR/BDR mechanism exists specifically to reduce the LSA flooding and adjacency count on broadcast/NBMA " +
        "networks from O(n²) to O(n): the DR originates the network-LSA (type 2) for the segment, listing every " +
        "attached router, and all non-DR/BDR routers (“DROTHER”) only need Full adjacencies with the DR " +
        "and BDR - they still see 2-Way neighbors for everyone else on the segment, just not Full.",
      "Non-preemption is a deliberate RFC 2328 design choice, not an implementation quirk: re-electing on every " +
        "priority or topology change would cause unnecessary churn (every DR/BDR change means the network-LSA is " +
        "re-originated and every DROTHER's adjacencies with the new DR/BDR must be rebuilt from scratch). The " +
        "tradeoff is that operators changing priorities to influence the DR must explicitly force re-election - " +
        "and in a live network, that forced re-election is itself a disruptive event worth scheduling carefully, " +
        "not a side effect to trigger casually.",
      "A subtlety worth knowing for troubleshooting: BDR election happens independently and simultaneously with DR " +
        "election in the same pass (RFC 2328 §9.4) - eligible routers first elect a BDR from among those not " +
        "declaring themselves DR, then elect the DR from among all eligible routers (preferring one that already " +
        "declared itself DR, to avoid unnecessary churn on router restart). This two-phase logic is why a router " +
        "restarting mid-election can occasionally produce a DR/BDR assignment that looks momentarily “out of " +
        "priority order” before settling.",
    ],
  },
  {
    id: "areas",
    title: "Areas, ABRs & LSA Types",
    blurb: "How OSPF scales past one flat topology, and what actually crosses an area boundary.",
    scenarios: ["03_inter_area", "11_area_mismatch"],
    beginner: [
      "A large OSPF network run as one single “area” means every router has to store and process every " +
        "other router's link-state information - that gets expensive to compute and slow to react to changes as " +
        "the network grows. Areas split the network into smaller pieces: routers inside an area only need the full " +
        "topology detail for that area, and areas exchange summarized reachability information instead.",
      "Every OSPF network has one backbone area, numbered 0 (“area 0”), and every other area must connect " +
        "to it - directly, or via a virtual link. In this lab, R1/R2/R3 are in area 0, and R4 is in area 1, " +
        "connected to the backbone through R2 and R3, which sit on the boundary between the two areas.",
      "A router with interfaces in more than one area - like R2 and R3 here - is called an Area Border Router " +
        "(ABR). ABRs are the translation point: they take the detailed topology of one area and advertise a " +
        "summarized version of it into the others.",
    ],
    pro: [
      "Both ends of a link must agree on the area ID configured for that link - it's carried in every Hello, and a " +
        "mismatch means the Hello is silently discarded (scenario 11): no adjacency forms, and there's nothing in " +
        "`show interface` to hint why, only `debug ip ospf hello` shows the rejected area ID.",
      { h: "The LSA types that actually matter day to day" },
      { ul: [
        "Type 1 (Router LSA) - every router originates one per area it's in, listing its own links and their " +
          "costs. Stays within the area.",
        "Type 2 (Network LSA) - originated by the DR on a multi-access segment, listing attached routers. Stays " +
          "within the area.",
        "Type 3 (Summary LSA) - originated by an ABR, advertising a route from one area into another (shown as " +
          "“O IA” in the routing table). This is what scenario 03 demonstrates.",
        "Type 4 (ASBR-Summary LSA) - an ABR telling other areas how to reach an ASBR that's in a different area.",
        "Type 5 (External LSA) - an ASBR advertising a route learned outside OSPF (redistribution). Floods " +
          "everywhere except stub/NSSA areas.",
        "Type 7 (NSSA-External LSA) - the NSSA-only equivalent of type 5, translated to type 5 at the NSSA's ABR.",
      ] },
      "`show ip ospf database` gives a per-type LSA count and lets you drill into each one; `show ip route ospf` " +
        "shows the resulting routing table with the type prefix (O, O IA, O E1/E2, O N1/N2) that tells you at a " +
        "glance which kind of route each one is, without having to cross-reference the database.",
    ],
    expert: [
      "Summary LSAs are not full topology - an ABR runs its own SPF for the area, then advertises just the " +
        "resulting cost to each intra-area destination as a type-3, one LSA per destination network. This is why " +
        "OSPF area design is inherently distance-vector-like *between* areas even though it's link-state *within* " +
        "an area - and why, unlike within a single area, routing loops between areas are theoretically possible " +
        "without split-horizon-style protection; OSPF avoids this in practice by forbidding an ABR from injecting " +
        "an inter-area route learned from one non-backbone area into another non-backbone area (all inter-area " +
        "traffic must transit area 0 - the hub-and-spoke area topology rule).",
      "Scenario 03's rollback demonstrates a real operational lag worth internalizing: withdrawing a route from " +
        "OSPF (removing `ip ospf area` from an interface) triggers a fast SPF recomputation that pulls the route " +
        "from the RIB almost immediately, but the ABR's self-originated type-3 LSA for that network isn't flushed " +
        "instantly - it has to be explicitly re-flooded as MaxAge (age 3600) and propagate through the area before " +
        "`show ip ospf database` stops listing it. A route disappearing from `show ip route` is not the same " +
        "moment as its LSA disappearing from the database, and tooling that only checks one or the other can give " +
        "a false read on convergence timing.",
      "Area 0 itself is special in one more way: it must be contiguous (or stitched together with virtual links " +
        "across a transit area), because every other area's inter-area routes are computed by an ABR that assumes " +
        "it has a working path to area 0. A partitioned backbone - two disconnected pieces both claiming to be " +
        "area 0 - is a classic large-network incident, and virtual links exist specifically as the (discouraged, " +
        "operationally fragile) emergency fix rather than a design pattern to build around.",
    ],
  },
  {
    id: "stub_nssa",
    title: "Stub, Totally Stubby & NSSA Areas",
    blurb: "Keeping external routing information out of areas that don't need it.",
    scenarios: ["04_stub_area", "06_nssa", "12_partial_stub_rollout", "14_dual_nssa_translator"],
    beginner: [
      "If an area only has one way out to the rest of the network, it doesn't need to know the detailed reason for " +
        "every external route out there - a single default route pointing at the ABR does the same job with far " +
        "less information to store and process. A “stub area” is exactly this: the ABR stops flooding " +
        "external (type 5) routes into it and instead injects a default route.",
      "In this lab, making area 1 a stub area (scenario 04) means R4 stops seeing individual external routes and " +
        "instead gets a single `O*IA 0.0.0.0/0` pointing back through R3.",
      "NSSA (Not-So-Stubby Area) is a variant for when the area itself needs to originate a few external routes " +
        "(say, a small site with its own internet break-out) while still not wanting to receive everyone else's " +
        "external routes. Scenario 06 shows R4 originating its own route this way.",
    ],
    pro: [
      "The stub flag is carried in the Hello packet's Options field (the E-bit) - every router attached to that " +
        "area must have it configured the same way, or the mismatch is treated exactly like an area-ID mismatch: " +
        "Hellos rejected, no adjacency. Scenario 12 demonstrates the real-world version of this: enabling stub on " +
        "only one of two routers attached to the same area during a staged rollout breaks that router's " +
        "adjacencies while its (still non-stub) peers on other links stay up - a confusing, asymmetric-looking " +
        "outage that's easy to misattribute to something else if you don't know to check the stub flag first.",
      "NSSA has its own extra wrinkle beyond stub: with more than one ABR attached to the NSSA, exactly one is " +
        "elected translator (type-7 to type-5), by highest Router ID among the NSSA's ABRs - not configurable by " +
        "priority, only by which router happens to have the higher ID. `area <n> nssa translate type7 always` " +
        "forces a specific ABR to translate regardless of that election; scenario 14 shows what actually happens " +
        "when it's applied to the *wrong* one: the properly-elected higher-Router-ID ABR doesn't originate a " +
        "competing LSA at all here, so `always` on the wrong router silently puts a different, un-elected router " +
        "in charge of every external route leaving that NSSA - worth verifying directly (`show ip ospf database " +
        "external`, checking the Advertising Router field) rather than assuming redundancy exists just because " +
        "two ABRs are NSSA-capable.",
      "Totally stubby (not modeled in this lab's scenarios, but common in real Cisco designs) goes one step " +
        "further and also suppresses inter-area (type 3) routes, leaving only the default - `area <n> stub " +
        "no-summary` on the ABR only (regular routers in the area just see `area <n> stub`, same as plain stub).",
    ],
    expert: [
      "RFC 3101 defines NSSA formally, including the P-bit (propagate bit) on type-7 LSAs, which tells the " +
        "translating ABR whether that specific LSA should be translated to type-5 at all (an NSSA ABR can " +
        "originate type-7 LSAs it explicitly does NOT want propagated to the backbone, by clearing the P-bit) - " +
        "useful for NSSA designs where only some locally-originated externals should ever reach the rest of the " +
        "network.",
      "The translator election itself (RFC 3101 §3.2) runs per-area among all NSSA-capable ABRs attached to " +
        "that area, purely on Router ID, independent of the `always` keyword's per-router override - `always` " +
        "changes whether *that* router translates, not who wins the election. What scenario 14 surfaces is an " +
        "implementation behavior worth treating as a real operational hazard rather than a theoretical curiosity: " +
        "a non-elected ABR translating unconditionally can end up as the sole source of translated LSAs for a " +
        "prefix in practice, meaning the properly-elected ABR's redundancy value for that route is not what an " +
        "operator would assume from the topology alone - always confirm which router is actually advertising the " +
        "type-5, not just which one has the higher Router ID on paper.",
      "Stub-area E-bit and NSSA N-bit are both carried the same way (Hello Options field), which is why a " +
        "half-migrated stub→NSSA change (some routers already switched, others not) fails exactly like a " +
        "plain stub mismatch - hellos silently dropped - which is also why scenario 04 and scenario 06 explicitly " +
        "cannot be applied to the same area simultaneously (the area can only be one type at a time), and why " +
        "rolling either one back fully before applying the other matters operationally, not just for this lab.",
    ],
  },
  {
    id: "external_redistribution",
    title: "External Routes, ASBRs & Redistribution",
    blurb: "Bringing routes from outside OSPF in - and the classic ways that goes wrong.",
    scenarios: ["05_external_e2", "13_subnets_keyword"],
    beginner: [
      "Not every route in a network comes from OSPF - a router might learn a route from a static configuration, a " +
        "different routing protocol, or a directly connected network that isn't running OSPF. “Redistribution” " +
        "is how a router takes a route it learned some other way and re-announces it into OSPF so the rest of the " +
        "OSPF network can use it.",
      "A router that does this redistribution is called an ASBR (Autonomous System Boundary Router). In this lab, " +
        "scenario 05 makes R1 an ASBR by redistributing a static route, which shows up on R3 and R4 as `O E2` in " +
        "the routing table - the “E” meaning “external.”",
      "Redistribution is powerful but easy to get subtly wrong: a command can succeed with no error and still not " +
        "do what you expected (scenario 13 shows a real, very common example of exactly this).",
    ],
    pro: [
      "OSPF has two flavors of external route, chosen by `metric-type`: E2 (the default) keeps the same metric " +
        "everywhere in the domain, ignoring the internal cost to reach the ASBR; E1 adds the internal OSPF cost to " +
        "the external metric, so E1 routes can have different costs depending on where you are in the network. E2 " +
        "is simpler and more common; E1 is used when the internal path cost should actually influence which ASBR " +
        "is preferred for a given external route.",
      "`redistribute static` (or `redistribute connected`, `redistribute bgp`, etc.) needs the `subnets` keyword " +
        "to redistribute anything that isn't on a natural classful network boundary - without it, only routes " +
        "that happen to be a “whole” classful network get redistributed, and everything else (which, on " +
        "any modern subnetted network, is nearly everything) is silently dropped: no error, no log, the command " +
        "just does less than it looks like it does. Scenario 13 demonstrates this directly - it's one of the most " +
        "commonly cited real OSPF gotchas for exactly that reason.",
      "Multiple redistribution points (more than one ASBR redistributing the same or overlapping routes) is a " +
        "real production pattern for redundancy, but it needs deliberate metric/metric-type/route-map design - " +
        "without it, you can get asymmetric routing or unexpected preference between ASBRs that's hard to reason " +
        "about after the fact.",
    ],
    expert: [
      "E1 vs E2 preference and tie-breaking: when both an E1 and E2 route exist for the same prefix, OSPF always " +
        "prefers E1, regardless of the numeric metric value - type dominates before metric comparison. Among " +
        "multiple E2 routes to the same prefix (equal external metric), OSPF breaks the tie using the internal " +
        "cost to reach each advertising ASBR - so E2's “metric doesn't change across the domain” " +
        "description is only true for the external portion; the effective path selection still depends on " +
        "internal topology when there's more than one ASBR.",
      "The `subnets` behavior traces back to OSPF's classful-redistribution default from RFC 2328-era Cisco IOS " +
        "conventions, predating widespread VLSM - it's a legacy default that almost never matches modern intent, " +
        "which is exactly why it's worth teaching as a named gotcha rather than an obscure edge case: any " +
        "redistribute statement into OSPF without `subnets` should be treated as almost certainly wrong until " +
        "proven otherwise for the specific network in question.",
      "Redistribution loops are the sharper version of the multiple-ASBR risk: redistributing OSPF routes back " +
        "into another protocol, which then gets redistributed back into OSPF at a different ASBR, can re-inject a " +
        "route with a fresher (lower) metric than the original, causing OSPF to prefer the looped-back path over " +
        "the real one - route-maps with explicit tagging (`set tag`, matched on re-entry) are the standard defense, " +
        "and any multi-protocol, multi-ASBR redistribution design should have that tagging discipline from the " +
        "start, not bolted on after an incident.",
    ],
  },
  {
    id: "cost_path_selection",
    title: "Cost, Reference Bandwidth & Path Selection",
    blurb: "How OSPF actually decides which path is “best” - and how that silently breaks at scale.",
    scenarios: ["07_cost_steering", "15_reference_bandwidth_mismatch"],
    beginner: [
      "When there's more than one way to reach a destination, OSPF picks the path with the lowest total cost - " +
        "the sum of the cost of every link along the way. By default, cost is derived from interface bandwidth: " +
        "faster links get a lower cost, so they're preferred.",
      "Scenario 07 shows this directly: at baseline, R4 has two equal-cost paths to R1 (through R2 and through " +
        "R3), so both are used at once (“ECMP”, equal-cost multi-path). Raising the cost on one link makes " +
        "the other the clear winner, and traffic shifts to use only that path.",
      "You can set cost by hand (`ip ospf cost N`) on any interface to steer traffic deliberately, without " +
        "touching bandwidth at all.",
    ],
    pro: [
      "The default cost formula is `reference-bandwidth ÷ interface-bandwidth`, and the default reference " +
        "bandwidth is 100 Mbps. That means, unmodified, any interface at 100 Mbps or faster gets cost 1 - a " +
        "Gigabit link and a 10-Gigabit link look identical to OSPF's default math, which is almost never what you " +
        "want on any network with faster-than-Fast-Ethernet links.",
      "`auto-cost reference-bandwidth <mbps>` raises that divisor so faster links get properly differentiated " +
        "costs again - but it's a per-router setting, and OSPF does **not** enforce that every router use the same " +
        "value. A mismatch (scenario 15) doesn't break the adjacency at all; IOS just logs a local, easy-to-miss " +
        "warning, and every neighbor stays Full while path costs silently diverge across the network - one router " +
        "can compute a completely different “best path” than its neighbors believe it should, with " +
        "nothing in `show ip ospf neighbor` to suggest anything is wrong.",
      "`show ip ospf` (bare, process-level) shows the configured reference bandwidth (“Reference bandwidth " +
        "unit is N mbps”) - checking this on every router is the fast way to catch a mismatch before it " +
        "causes a routing-preference incident.",
    ],
    expert: [
      "Because reference-bandwidth changes cost for *every* interface on the router simultaneously, changing it on " +
        "a live network recomputes the entire local view of path costs in one step - on a large network this is " +
        "exactly the kind of change that should be scheduled and rolled out to all routers in a single maintenance " +
        "window, not incrementally, precisely because the “no adjacency impact” property that makes it " +
        "seem safe is the same property that lets a partial rollout go unnoticed until traffic patterns look wrong.",
      "ECMP path count and load-balancing behavior (per-packet vs per-destination/per-flow) are platform and " +
        "forwarding-plane decisions, not something OSPF itself controls beyond identifying which next-hops are " +
        "equal-cost - `maximum-paths` (default varies by platform, often 4 or 8) bounds how many of those equal-cost " +
        "paths actually get installed in the RIB even when more exist.",
      "Cost is per-interface, not per-neighbor - on a shared broadcast segment, every neighbor reachable through " +
        "that interface uses the same outbound cost, which is worth remembering when a multi-access segment mixes " +
        "routers you'd otherwise want to prefer differently; achieving that requires a design change (subinterfaces, " +
        "a different topology), not a per-neighbor cost knob, because OSPF has none.",
    ],
  },
  {
    id: "fast_convergence",
    title: "BFD & Fast Convergence",
    blurb: "Detecting a dead neighbor in milliseconds instead of tens of seconds - and what to do when that's not an option.",
    scenarios: ["08_bfd", "16_fast_hello_no_bfd"],
    beginner: [
      "By default, OSPF only notices a neighbor is gone when its dead timer expires - 40 seconds at this lab's " +
        "baseline hello-interval of 10s. For many networks that's fine; for others (financial trading, voice, " +
        "anything latency-sensitive) 40 seconds of a route pointing at a dead path is a real, felt outage.",
      "BFD (Bidirectional Forwarding Detection) is a lightweight, protocol-independent “is this neighbor still " +
        "there” heartbeat that runs much faster than routing-protocol hellos - tens of milliseconds instead of " +
        "seconds - and tells OSPF to react immediately when it stops hearing back, instead of waiting out the full " +
        "dead timer.",
      "This particular lab environment (Dynamips software emulation) can't run BFD reliably - see scenario 08's " +
        "notes - which is itself a useful, real lesson: fast-detection features have real infrastructure " +
        "requirements, and not every platform can deliver on them, even when the configuration is accepted without " +
        "complaint.",
    ],
    pro: [
      "BFD registers itself with OSPF per-interface (`ip ospf bfd`) after being configured on the interface itself " +
        "(`bfd interval <ms> min_rx <ms> multiplier <n>`). Once registered, BFD - not the OSPF hello/dead timer - " +
        "becomes the primary failure-detection mechanism for that neighbor; OSPF still sends hellos, but the " +
        "dead-timer countdown is effectively pre-empted by BFD's much faster down notification.",
      "When BFD genuinely isn't viable (older hardware, some virtualized/emulated platforms, or a vendor " +
        "interop concern), OSPF's own `ip ospf dead-interval minimal hello-multiplier N` gives a real, if slower, " +
        "alternative: N hellos per second, neighbor declared down after 1 second of silence. Scenario 16 " +
        "demonstrates exactly this - roughly 1-second detection without touching BFD at all, safely, on a platform " +
        "where BFD itself is unstable.",
      "Both approaches trade CPU/interrupt load for detection speed - fast hellos and BFD both mean more packets " +
        "per second that the control plane has to process on every participating interface, which matters more on " +
        "software-forwarded or heavily-loaded platforms than on dedicated hardware-forwarding routers.",
    ],
    expert: [
      "BFD's own state machine (RFC 5880) is independent of any single routing protocol - a single BFD session per " +
        "link can be shared by OSPF, BGP, static routes, and others simultaneously, all reacting to the same " +
        "liveness signal, which is part of why it's preferred at scale over each protocol running its own " +
        "fast-hello mechanism separately.",
      "The instability seen on this lab's Dynamips platform (BFD wedging the IOS scheduler - see docs/lab.md for " +
        "the exact signature) is a concrete illustration of a broader principle: BFD's whole value proposition " +
        "depends on the control plane being able to service it in near-real-time, which is a genuinely hard " +
        "guarantee to make on a software-forwarding or CPU-emulated platform under load - the same aggressive " +
        "timers that make BFD useful on real hardware are exactly what exposes scheduling weaknesses on platforms " +
        "that can't guarantee that timing. This is a real (if less severe) risk to model even on production " +
        "software routers under sustained high CPU load, not just an emulation artifact.",
      "Sub-second OSPF-native detection (`dead-interval minimal`) doesn't have BFD's cross-protocol sharing " +
        "benefit and is inherently coupled to hello processing load, but it has one advantage worth knowing: it " +
        "requires no separate protocol/session state beyond what OSPF already tracks, which makes its failure mode " +
        "simpler to reason about than a BFD session that can itself become the thing failing, independent of the " +
        "link or the routing protocol above it.",
    ],
  },
  {
    id: "monitoring",
    title: "IP SLA & Operational Monitoring",
    blurb: "Measuring the network, not just routing through it - and how that data leaves the router.",
    scenarios: [],
    beginner: [
      "OSPF tells you the routing table is converged - it doesn't tell you whether the path actually performs " +
        "well. IP SLA is Cisco's built-in tool for actively probing the network (sending real test traffic, like " +
        "pings, on a schedule) and recording the results: round-trip time, packet loss, jitter.",
      "In this lab, R4 runs an IP SLA ICMP echo probe to R1's loopback every 10 seconds, and the result (`show ip " +
        "sla statistics`) is what feeds the RTT numbers you see on the Monitor tab and in Grafana.",
      "The bigger picture: this app polls every router every 20 seconds (neighbor states, interface roles, route " +
        "counts, IP SLA, BFD), publishes what changed to Kafka, and a separate exporter turns those Kafka messages " +
        "into Prometheus metrics that Grafana graphs over time - so you get both a live view (Monitor, Kafka tabs) " +
        "and a historical one (Grafana) from the same underlying data.",
    ],
    pro: [
      "`ip sla <id>` defines the probe (type - icmp-echo here, but IP SLA supports many others: UDP jitter, HTTP, " +
        "DNS, TCP connect, and more), and `ip sla schedule` starts it running. `show ip sla statistics` gives the " +
        "latest result; `show ip sla configuration` shows what's actually configured.",
      "This app's monitor polls `show ip ospf neighbor`, `show ip ospf interface`, `show ip route ospf`, `show ip " +
        "sla statistics`, and `show bfd neighbors` (where applicable) on every router, on a fixed interval " +
        "(`OSPF_POLL_INTERVAL`, 20s by default) - not event-driven, since polling read-only `show` commands over " +
        "SSH is far simpler and more portable across IOS versions than trying to hook syslog or SNMP traps.",
      "Every poll produces two kinds of Kafka message: a full per-router snapshot (`ospf.neighbor.snapshots`, " +
        "every poll, every router) and, only when something actually changed since the last poll, an event " +
        "(`ospf.neighbor.events` - state changes, DR/BDR role changes, reachability changes). `ospf.config.changes` " +
        "is separate again: it's written directly when a scenario applies, rolls back, or the lab resets to " +
        "baseline - not from polling at all. The Kafka tab shows all three live, straight from the broker.",
    ],
    expert: [
      "The snapshot/event split exists so downstream consumers can choose their own tradeoff: the exporter turns " +
        "every snapshot into current-state Prometheus gauges (so a metric like `ospf_neighbor_state` always " +
        "reflects the last poll, whether or not anything changed), while the event stream is what a human-facing " +
        "live feed (Monitor tab, alerting) actually wants to consume - a full snapshot every 20 seconds would be " +
        "noisy and mostly redundant for that purpose.",
      "This is a genuinely useful small-scale model of a production network telemetry pipeline: poll or " +
        "instrument the actual network state, publish structured events onto a durable log (Kafka) that decouples " +
        "producers from consumers, and let each consumer (a metrics exporter, a dashboard, an alerting system) " +
        "read the same stream independently, at its own pace, without needing to know about or block on any other " +
        "consumer. The same pattern scales conceptually from this 4-router lab to a real multi-thousand-device " +
        "network - what changes is the polling/telemetry source (streaming telemetry, SNMP, syslog instead of " +
        "SSH+show-commands) and the consumer count, not the core shape of the pipeline.",
      "A practical operational note from building this: fail-soft matters at every stage - the Kafka producer " +
        "(`bus.py`) never blocks or crashes the poller if Kafka is unreachable, and the UI's Kafka tail " +
        "(`kafka_tail.py`) is a completely separate, best-effort consumer that simply shows nothing if Kafka is " +
        "down, rather than taking the whole dashboard down with it. Telemetry infrastructure being unavailable " +
        "should never be able to take down the thing it's monitoring, or the operator's ability to see it directly.",
    ],
  },
];

export const LEVELS = [
  { id: "beginner", label: "Beginner" },
  { id: "pro", label: "Pro" },
  { id: "expert", label: "Expert" },
];
