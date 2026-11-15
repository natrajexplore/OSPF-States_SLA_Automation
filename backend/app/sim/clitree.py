"""IOS command trees, abbreviation parsing, Tab completion and `?` help for the simulated routers' CLI (sshd.py).

A tree is built from a spec, one command per line: `a|b` = alternatives at that position, `<a>` = one argument (address,
number, name), `<if>` = an interface name (Tab completes its type: `e` -> `Ethernet`), `<r>` = the rest of the line
(a description, a banner, a regular expression).

Like IOS:
  * a keyword can be abbreviated while it stays unique among the words allowed at that point (`sh ip int br`);
  * Tab completes the last word when it is unique (`sh ip ospf ne<Tab>` -> `sh ip ospf neighbor `), and otherwise
    redisplays the line;
  * `?` right after a word lists the keywords it can start (`sh ip o?` -> `ospf`), `?` after a space lists what can
    follow, with a one-line description, `WORD` for an argument and `<cr>` when the command is complete.
"""
from __future__ import annotations

LEAF = "$"
ARG = "<a>"
IFMARK = "#if"

# interface types of a 7206VXR with the PA-8E and the C7200-IO-FE, plus the logical ones
IF_TYPES = {"Ethernet": "IEEE 802.3", "FastEthernet": "FastEthernet IEEE 802.3", "Loopback": "Loopback interface",
            "Null": "Null interface", "Tunnel": "Tunnel interface"}


def build(spec: str) -> dict:
    root: dict = {}
    for line in spec.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        nodes = [root]
        for tok in line.split():
            nxt = []
            for node in nodes:
                if tok in ("<a>", "<if>", "<r>"):
                    child = node.setdefault(ARG, {})
                    if tok == "<if>":
                        node[IFMARK] = True
                    if tok == "<r>":
                        child[ARG] = child                # consumes every remaining word
                        child[LEAF] = True
                    nxt.append(child)
                else:
                    for alt in tok.split("|"):
                        nxt.append(node.setdefault(alt, {}))
            nodes = nxt
        for node in nodes:
            node[LEAF] = True
    return root


def _kws(node: dict) -> list[str]:
    return [w for w in node if w not in (LEAF, ARG, IFMARK)]


class ParseError(Exception):
    def __init__(self, kind: str, pos: int = 0, words: list[str] | None = None) -> None:
        super().__init__(kind)
        self.kind, self.pos, self.words = kind, pos, words or []


def parse(line: str, tree: dict) -> list[str]:
    """Expand IOS abbreviations along the command tree. Raises ParseError(invalid / ambiguous / incomplete)."""
    toks = line.split()
    node, out, col = tree, [], 0
    for tok in toks:
        col = line.find(tok, col)
        low = tok.lower()
        kws = _kws(node)
        if low in kws:
            out.append(low)
            node = node[low]
        else:
            hits = [w for w in kws if w.startswith(low)]
            if len(hits) == 1:
                out.append(hits[0])
                node = node[hits[0]]
            elif len(hits) > 1:
                raise ParseError("ambiguous", col)
            elif ARG in node:
                out.append(tok)
                node = node[ARG]
            else:
                raise ParseError("invalid", col)
        col += len(tok)
    if LEAF not in node:
        raise ParseError("incomplete", len(line))
    return out


def walk(toks: list[str], tree: dict) -> dict | None:
    """The node reached after `toks` (abbreviations allowed), or None when they do not form a command start."""
    node = tree
    for tok in toks:
        low = tok.lower()
        kws = _kws(node)
        hits = [w for w in kws if w == low] or [w for w in kws if w.startswith(low)]
        if len(hits) == 1:
            node = node[hits[0]]
        elif ARG in node:
            node = node[ARG]
        else:
            return None
    return node


def help_for(line: str, tree: dict) -> list[str]:
    """`?`: the words that can follow (`show ?`) or complete the last one (`sh ip o?`)."""
    partial = not line.endswith(" ") and line.strip() != ""
    toks = line.split()
    prefix = toks.pop().lower() if partial and toks else ""
    node = walk(toks, tree)
    if node is None:
        return []
    words = sorted(w for w in _kws(node) if w.startswith(prefix))
    if node.get(IFMARK):
        words += [t for t in IF_TYPES if t.lower().startswith(prefix)]
    if not partial:
        if ARG in node and not node.get(IFMARK):
            words.append("WORD")
        if LEAF in node:
            words.append("<cr>")
    return words


def complete(line: str, tree: dict) -> str | None:
    """Tab: the line with its last word completed, or None when it is not unique (or there is nothing to complete)."""
    if not line.strip() or line.endswith(" "):
        return None
    toks = line.split()
    prefix = toks[-1]
    node = walk(toks[:-1], tree)
    if node is None:
        return None
    low = prefix.lower()
    kws = _kws(node)
    if low in kws:
        word, space = low, True
    else:
        hits = [(w, True) for w in kws if w.startswith(low)]
        if node.get(IFMARK):
            hits += [(t, False) for t in IF_TYPES if t.lower().startswith(low)]
        if len(hits) != 1:
            return None
        word, space = hits[0]
    return line[: len(line) - len(prefix)] + word + (" " if space else "")


# -- descriptions shown by `?` ----------------------------------------------------------------------------------------
DESC = {
    # exec
    "show": "Show running system information", "configure": "Enter configuration mode", "ping": "Send echo messages",
    "traceroute": "Trace route to destination", "write": "Write running configuration to memory, network, or terminal",
    "copy": "Copy from one file to another", "clear": "Reset functions", "enable": "Turn on privileged commands",
    "disable": "Turn off privileged commands", "exit": "Exit from the EXEC", "logout": "Exit from the EXEC",
    "quit": "Exit from the EXEC", "terminal": "Set terminal line parameters", "dir": "List files on a filesystem",
    "reload": "Halt and perform a cold restart", "who": "List active connections", "help": "Description of the interactive help system",
    "end": "Exit configuration mode", "do": "To run exec commands in config mode",
    # show
    "running-config": "Current operating configuration", "startup-config": "Contents of startup configuration",
    "interfaces": "Interface status and configuration", "ip": "IP information", "ipv6": "IPv6 information",
    "version": "System hardware and software status", "inventory": "Show the physical inventory",
    "logging": "Show the contents of logging buffers", "cdp": "CDP information", "arp": "ARP table",
    "users": "Display information about terminal lines", "history": "Display the session command history",
    "clock": "Display the system clock", "processes": "Active process statistics", "memory": "Memory statistics",
    "flash:": "display information about flash: file system", "disk0:": "display information about disk0: file system",
    "controllers": "Interface controller status", "diag": "Show diagnostic information for port adapters/modules",
    "bfd": "BFD protocol info", "route-map": "route-map information", "ntp": "Network time protocol",
    "line": "TTY line information", "privilege": "Show current privilege level", "snmp": "snmp statistics",
    "access-lists": "List access lists", "standby": "HSRP information", "track": "Tracking information",
    "boot": "show boot attributes", "environment": "Environmental monitor statistics",
    "tech-support": "Show system information for Tech-Support", "debugging": "State of each debugging option",
    "hosts": "IP domain-name, lookup style, nameservers, and host table",
    "protocols": "IP routing protocol process parameters and statistics", "route": "IP routing table",
    "ospf": "OSPF information", "sla": "IP Service Level Agreement", "cef": "Cisco Express Forwarding",
    "vrf": "VPN Routing/Forwarding instance information", "interface": "IP interface status and configuration",
    "neighbor": "Neighbor list", "database": "Database summary", "border-routers": "Border and Boundary Router Information",
    "statistics": "Various OSPF Statistics", "traffic": "Traffic related statistics", "events": "OSPF event information",
    "rib": "Routing information base (RIB)", "virtual-links": "Virtual link information",
    "summary-address": "Summary-address redistribution Information", "brief": "Brief summary of IP status and configuration",
    "detail": "Show detailed information", "details": "Show detailed information", "description": "Show interface description",
    "summary": "Summary of the information", "configuration": "IP SLAs Configuration", "neighbors": "CDP neighbor entries",
    "connected": "Connected networks", "static": "Static routes", "local": "Local routes", "cpu": "Show CPU usage information",
    "sorted": "Sort output", "status": "Status of NTP", "associations": "NTP associations",
    "router": "Router link states", "network": "Network link states", "asbr-summary": "Summary ASBR link states",
    "external": "External link states", "nssa-external": "NSSA External link states",
    "database-summary": "Summary of database", "length": "Set number of lines on a screen",
    "width": "Set width of the display terminal", "monitor": "Copy debug output to the current terminal line",
    "counters": "Clear counters on one or all interfaces", "process": "Reset OSPF process",
    "repeat": "specify repeat count", "source": "specify source address or name", "size": "specify datagram size",
    # configure
    "hostname": "Set system's network name",
    "username": "Establish User Name Authentication", "service": "Modify use of network based services",
    "banner": "Define a login banner", "access-list": "Add an access list entry",
    "no": "Negate a command or set its defaults", "default": "Set a command to its defaults",
    "address": "Set the IP address of an interface", "shutdown": "Shutdown the selected interface",
    "duplex": "Configure duplex operation.", "speed": "Configure speed operation.", "bandwidth": "Set bandwidth informational parameter",
    "mtu": "Set the interface Maximum Transmission Unit (MTU)", "hello-interval": "Time between HELLO packets",
    "dead-interval": "Interval after which a neighbor is declared dead", "cost": "Interface cost",
    "priority": "Router priority", "network-type": "Network type", "authentication": "Enable authentication",
    "authentication-key": "Authentication password (key)", "message-digest-key": "Message digest authentication password (key)",
    "router-id": "router-id for this OSPF process", "area": "OSPF area parameters",
    "passive-interface": "Suppress routing updates on an interface", "redistribute": "Redistribute information from another routing protocol",
    "default-information": "Control distribution of default information", "auto-cost": "Calculate OSPF interface cost according to bandwidth",
    "timers": "Adjust routing timers", "max-metric": "Set maximum metric", "log-adjacency-changes": "Log changes in adjacency state",
    "distance": "Define an administrative distance", "maximum-paths": "Forward packets over multiple paths",
    "default-metric": "Set metric of redistributed routes", "stub": "Specify a stub area", "nssa": "Specify a NSSA area",
    "range": "Summarize routes matching address/mask (border routers only)", "virtual-link": "Define a virtual link and its parameters",
    "no-summary": "Do not send summary LSA into the area", "translate": "Translate LSA", "subnets": "Consider subnets for redistribution into OSPF",
    "metric": "Metric for redistributed routes", "metric-type": "OSPF/IS-IS exterior metric type for redistributed routes",
    "icmp-echo": "ICMP Echo Operation", "frequency": "Frequency of an operation", "timeout": "Timeout of an operation",
    "threshold": "Operation threshold in milliseconds", "tag": "User defined tag", "schedule": "Schedule probe",
    "match": "Match values from routing table", "set": "Set values in destination routing protocol",
    "permit": "Route map permits set operations", "deny": "Route map denies set operations",
    "login": "Enable password checking", "transport": "Define transport protocols for line",
    "exec-timeout": "Set the EXEC timeout", "secret": "Specify the secret for the user", "password": "Specify the password for the user",
    "unicast-routing": "Enable unicast routing", "domain": "IP DNS Resolver", "domain-name": "Define the default domain name",
    "forwarding": "Configure forwarding table", "instance": "Instance ID",
    "vty": "Virtual terminal", "console": "Primary terminal line", "buffered": "Set buffered logging parameters",
    "timestamps": "Timestamp debug/log messages", "password-encryption": "Encrypt system passwords",
    "motd": "Set Message of the Day banner", "always": "Always advertise default route", "originate": "Distribute a default route",
    "reference-bandwidth": "Use reference bandwidth method to assign OSPF cost", "throttle": "OSPF throttle timers",
    "spf": "OSPF SPF throttle timers", "router-lsa": "Maximum metric in self-originated router-LSAs",
    "md5": "Use MD5 algorithm", "point-to-point": "Specify OSPF point-to-point network",
    "broadcast": "Specify OSPF broadcast multi-access network", "non-broadcast": "Specify OSPF NBMA network",
    "point-to-multipoint": "Specify OSPF point-to-multipoint network",
    "include": "Include lines that match", "exclude": "Exclude lines that match", "begin": "Begin with the line that matches",
    "section": "Filter a section of output", "count": "Count number of lines which match regexp",
    "|": "Output modifiers", "mtu-ignore": "Ignores the MTU in DBD packets",
    "retransmit-interval": "Time between retransmitting lost link state advertisements",
    "transmit-delay": "Link state transmit delay", "WORD": "", "<cr>": "",
}
CFG_DESC = {"description": "Interface specific description", "ntp": "Configure NTP", "cdp": "Global CDP configuration subcommands",
            "memory": "Write to NV memory", "ip": "Global IP configuration subcommands", "ipv6": "Global IPv6 configuration commands",
             "router": "Enable a routing process", "logging": "Modify message logging facilities",
             "line": "Configure a terminal line", "route-map": "Create route-map or enter route-map command mode",
             "enable": "Modify enable password parameters", "ospf": "OSPF interface commands", "bfd": "BFD interface configuration commands",
             "network": "Enable routing on an IP network", "sla": "IP Service Level Agreement", "vrf": "Configure an IP VPN Routing/Forwarding instance",
             "route": "Establish static routes", "default": "Set a command to its defaults",
             "address": "Set the IP address of an interface", "interface": "Select an interface to configure"}


def describe(words: list[str], config: bool = False) -> str:
    """IOS `?` output: one `  word   description` row per choice."""
    if not words:
        return ""
    width = max(len(w) for w in words) + 3
    rows = []
    for w in words:
        d = (CFG_DESC.get(w) if config else None) or DESC.get(w) or IF_TYPES.get(w, "")
        if w == "WORD":
            d = "Argument"
        rows.append(f"  {w:<{width}}{d}".rstrip())
    return "\n".join(rows) + "\n"


def columns(words: list[str]) -> str:
    """`sh?`: the matching keywords on one line, as IOS prints them."""
    return "  ".join(words) + "  \n" if words else ""


# -- configuration trees ------------------------------------------------------------------------------------------------
_GLOBAL_SPEC = """
hostname <a>
interface <if>
interface <if> <a>
router ospf <a>
router ospf <a> vrf <a>
ipv6 router ospf <a>
ipv6 unicast-routing
ipv6 cef
ipv6 route <a> <a>
ipv6 route <a> <a> <a>
ip route <a> <a> <a>
ip route <a> <a> <a> <a>
ip route vrf <a> <a> <a> <a>
ip route vrf <a> <a> <a> <a> <a>
ip sla <a>
ip sla schedule <a> life forever|<a> start-time now
ip domain-name <a>
ip domain name <a>
ip domain lookup
ip vrf <a>
ip cef
ip ssh version <a>
ip ssh time-out <a>
route-map <a>
route-map <a> permit|deny
route-map <a> permit|deny <a>
username <a> secret <r>
username <a> password <r>
username <a> privilege <a> secret|password <r>
enable secret <r>
enable password <r>
line vty <a>
line vty <a> <a>
line console|con <a>
logging buffered
logging buffered <a>
logging host <a>
logging console|monitor
service timestamps
service timestamps debug|log datetime msec
service password-encryption
banner motd|login|exec <r>
ntp server <a>
cdp run
access-list <a> permit|deny <r>
no <r>
default <r>
end
exit
"""
_IF_SPEC = """
ip address <a> <a>
ip address <a> <a> secondary
ip ospf <a> area <a>
ip ospf hello-interval|dead-interval|cost|priority|retransmit-interval|transmit-delay <a>
ip ospf network point-to-point|broadcast|non-broadcast|point-to-multipoint
ip ospf authentication
ip ospf authentication message-digest|null
ip ospf authentication-key <r>
ip ospf message-digest-key <a> md5 <r>
ip ospf bfd
ip ospf mtu-ignore
ip mtu <a>
ip vrf forwarding <a>
ipv6 address <a>
ipv6 address <a> link-local
ipv6 enable
ipv6 ospf <a> area <a>
ipv6 ospf <a> area <a> instance <a>
ipv6 ospf hello-interval|dead-interval|cost|priority <a>
ipv6 ospf network point-to-point|broadcast
bfd interval <a> min_rx <a> multiplier <a>
description <r>
shutdown
duplex auto|full|half
speed 10|100|auto
bandwidth <a>
mtu <a>
cdp enable
"""
_OSPF_SPEC = """
router-id <a>
network <a> <a> area <a>
area <a> stub
area <a> stub no-summary
area <a> nssa
area <a> nssa no-summary|default-information-originate
area <a> nssa translate type7 always
area <a> range <a> <a>
area <a> virtual-link <a>
area <a> authentication
area <a> authentication message-digest
passive-interface <if>
passive-interface <if> <a>
passive-interface default
redistribute connected|static
redistribute connected|static subnets
redistribute connected|static metric <a>
redistribute connected|static metric <a> subnets
redistribute connected|static metric <a> metric-type 1|2
redistribute connected|static metric <a> metric-type 1|2 subnets
redistribute connected|static metric-type 1|2
redistribute connected|static metric-type 1|2 subnets
default-information originate
default-information originate always
default-information originate always metric <a>
default-information originate always metric <a> metric-type 1|2
default-information originate metric <a>
auto-cost reference-bandwidth <a>
timers throttle spf <a> <a> <a>
max-metric router-lsa
max-metric router-lsa on-startup <a>
summary-address <a> <a>
summary-address <a>
log-adjacency-changes
log-adjacency-changes detail
bfd all-interfaces
distance <a>
maximum-paths <a>
default-metric <a>
"""
_SLA_SPEC = """
icmp-echo <a>
icmp-echo <a> source-ip|source-interface <a>
frequency <a>
timeout <a>
threshold <a>
tag <r>
tos <a>
request-data-size <a>
vrf <a>
"""
_RMAP_SPEC = """
match ip address <r>
match ip address prefix-list <r>
match interface <if>
match route-type internal|external|local
match tag <a>
set metric <a>
set metric-type type-1|type-2
set tag <a>
description <r>
"""
_LINE_SPEC = """
login
login local
transport input ssh|telnet|all|none
transport output ssh|telnet|all|none
exec-timeout <a>
exec-timeout <a> <a>
logging synchronous
password <r>
privilege level <a>
"""

_CFG_TREES: dict[str, dict] = {}


def config_tree(mode: tuple, exec_tree: dict) -> dict:
    """The command tree of a configuration mode: its own commands, the global ones (IOS falls back to them) and `do`."""
    kind = mode[0]
    if kind == "other" and len(mode) > 1 and str(mode[1]).startswith("line"):
        kind = "line"
    if kind not in _CFG_TREES:
        sub = {"if": _IF_SPEC, "ospf": _OSPF_SPEC, "ospf6": _OSPF_SPEC, "sla": _SLA_SPEC, "rmap": _RMAP_SPEC,
               "line": _LINE_SPEC}.get(kind, "")
        tree = build(sub + _GLOBAL_SPEC)
        # `no` / `default` take any command of the mode, arguments optional (`no ip ospf cost`)
        neg = build(sub + _GLOBAL_SPEC)
        _optional_args(neg)
        tree["no"] = neg
        tree["default"] = neg
        tree["do"] = exec_tree
        _CFG_TREES[kind] = tree
    return _CFG_TREES[kind]


def _optional_args(node: dict, seen: set | None = None) -> None:
    """Under `no`, a command is complete as soon as an argument is expected."""
    seen = seen if seen is not None else set()
    if id(node) in seen:
        return
    seen.add(id(node))
    if ARG in node:
        node[LEAF] = True
    for k, v in list(node.items()):
        if isinstance(v, dict):
            _optional_args(v, seen)


PIPE_TREE = build("include|exclude|begin|section|count <r>")


# -- what `?` says about an argument, and words whose meaning depends on the keyword before them -----------------------
_A = "A.B.C.D"
ARG_HINT: dict = {
    ("router", "ospf", 0): [("<1-65535>", "Process ID")], ("ip", "ospf", 0): [("<1-65535>", "Process ID")],
    ("ipv6", "ospf", 0): [("<1-65535>", "Process ID")],
    ("area", 0): [("<0-4294967295>", "OSPF area ID as a decimal value"), (_A, "OSPF area ID in IP address format")],
    ("hello-interval", 0): [("<1-65535>", "Seconds")], ("dead-interval", 0): [("<1-65535>", "Seconds")],
    ("retransmit-interval", 0): [("<1-65535>", "Seconds")], ("transmit-delay", 0): [("<1-65535>", "Seconds")],
    ("cost", 0): [("<1-65535>", "Cost")], ("priority", 0): [("<0-255>", "Priority")],
    ("address", 0): [(_A, "IP address")], ("address", 1): [(_A, "IP subnet mask")],
    ("network", 0): [(_A, "Network number")], ("network", 1): [(_A, "OSPF wild card bits")],
    ("route", 0): [(_A, "Destination prefix")], ("route", 1): [(_A, "Destination prefix mask")],
    ("route", 2): [(_A, "Forwarding router's address")],
    ("router-id", 0): [(_A, "OSPF router-id in IP address format")],
    ("hostname", 0): [("WORD", "This system's network name")],
    ("description", 0): [("LINE", "Up to 240 characters describing this interface")],
    ("ping", 0): [("WORD", "Ping destination address or hostname")],
    ("traceroute", 0): [("WORD", "Trace route to destination address or hostname")],
    ("length", 0): [("<0-512>", "Number of lines on screen (0 for no pausing)")],
    ("width", 0): [("<0-512>", "Number of characters on a screen line")],
    ("sla", 0): [("<1-2147483647>", "Entry Number")], ("schedule", 0): [("<1-2147483647>", "Entry number")],
    ("frequency", 0): [("<1-604800>", "Frequency in seconds (default 60)")],
    ("metric", 0): [("<0-16777214>", "OSPF default metric")],
    ("vrf", 0): [("WORD", "VPN Routing/Forwarding instance name")],
    ("icmp-echo", 0): [("Hostname or A.B.C.D", "Destination IP address or hostname, broadcast disallowed")],
    ("mtu", 0): [("<68-1500>", "MTU (bytes)")], ("bandwidth", 0): [("<1-10000000>", "Bandwidth in kilobits")],
    ("reference-bandwidth", 0): [("<1-4294967>", "The reference bandwidth in terms of Mbits per second")],
    ("range", 0): [(_A, "IP address to match")], ("range", 1): [(_A, "IP mask for address")],
    ("summary-address", 0): [(_A, "IP summary address")], ("summary-address", 1): [(_A, "Summary mask")],
    ("secret", 0): [("LINE", "The UNENCRYPTED (cleartext) user secret")],
    ("password", 0): [("LINE", "The UNENCRYPTED (cleartext) user password")],
    ("username", 0): [("WORD", "User name")], ("route-map", 0): [("WORD", "Route map tag")],
    ("instance", 0): [("<0-255>", "Instance ID")], ("timeout", 0): [("<0-604800000>", "Timeout in milliseconds")],
    ("threshold", 0): [("<0-60000>", "Millisecond threshold value")],
    ("vty", 0): [("<0-1869>", "First Line number")], ("vty", 1): [("<1-1869>", "Last Line number")],
    ("privilege", 0): [("<0-15>", "User privilege level")], ("maximum-paths", 0): [("<1-32>", "Number of paths")],
    ("distance", 0): [("<1-255>", "Administrative distance")], ("tag", 0): [("<0-4294967295>", "Tag value")],
    ("virtual-link", 0): [(_A, "ID (IP addr) associated with virtual link neighbor")],
    ("message-digest-key", 0): [("<1-255>", "Key ID")], ("md5", 0): [("LINE", "The OSPF password (key)")],
    ("authentication-key", 0): [("LINE", "The OSPF password (key)")],
}
CTX_DESC = {
    ("ospf", "network"): "Network type", ("ospf", "interface"): "Interface information",
    ("ospf", "bfd"): "Enable BFD on this interface", ("ospf", "mtu-ignore"): "Ignores the MTU in DBD packets",
    ("ospf", "retransmit-interval"): "Time between retransmitting lost link state advertisements",
    ("ospf", "transmit-delay"): "Link state transmit delay", ("router", "ospf"): "Open Shortest Path First (OSPF)",
    ("ospf", "database"): "Database summary", ("show", "interfaces"): "Interface status and configuration",
    ("ipv6", "router"): "Enable an IPV6 routing process", ("ipv6", "address"): "Configure IPv6 address on interface",
    ("ipv6", "ospf"): "OSPF interface commands", ("ip", "sla"): "IP Service Level Agreement",
}


def context(line: str, tree: dict) -> tuple[str, str, int]:
    """(keyword before the last keyword, last keyword, arguments typed since it) for the complete words of `line`."""
    toks = line.split() if line.endswith(" ") or not line.strip() else line.split()[:-1]
    node, kws, nargs = tree, ["", ""], 0
    for tok in toks:
        low = tok.lower()
        cand = _kws(node)
        hits = [w for w in cand if w == low] or [w for w in cand if w.startswith(low)]
        if len(hits) == 1:
            kws.append(hits[0])
            nargs = 0
            node = node[hits[0]]
        elif ARG in node:
            nargs += 1
            node = node[ARG]
        else:
            break
    return kws[-2], kws[-1], nargs


def describe_ctx(words: list[str], line: str, tree: dict, config: bool = False) -> str:
    """`?` with the argument named as IOS names it (`<1-65535>  Process ID`) and context-dependent descriptions."""
    grand, parent, nargs = context(line, tree)
    hints = ARG_HINT.get((grand, parent, nargs)) or ARG_HINT.get((parent, nargs))
    rows: list[tuple[str, str]] = []
    for w in words:
        if w == "WORD" and hints:
            rows += hints
            continue
        d = CTX_DESC.get((parent, w)) or (CFG_DESC.get(w) if config else None) or DESC.get(w) or IF_TYPES.get(w, "")
        rows.append((w, "Argument" if w == "WORD" else d))
    if not rows:
        return ""
    width = max(len(w) for w, _ in rows) + 3
    return "\n".join(f"  {w:<{width}}{d}".rstrip() for w, d in rows) + "\n"
