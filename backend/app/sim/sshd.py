"""SSH login to the simulated routers, so PuTTY (or any SSH client) can open R1..R4 in simulation mode.

One SSH server per router of the inventory, on consecutive ports from OSPF_SIM_SSH_PORT (R1 2201, R2 2202, ...). Login
with any `username` of the router's configuration (cisco / lab). The shell is an IOS exec and configuration CLI on top
of the same SimLab the dashboard uses, so a change typed in PuTTY shows up in the 3D view, the monitor and Grafana, and
the dashboard's Apply / Rollback shows up in PuTTY (`terminal monitor` prints its %OSPF-5-ADJCHG messages live).

Like IOS, commands are parsed against a command tree: every keyword can be abbreviated as long as it stays unique
among the words allowed at that point (`sh ip int br`, `sh ip pro`, `conf t`, `wr`), an ambiguous abbreviation gives
"% Ambiguous command", a missing keyword "% Incomplete command.", and `?` lists what can follow.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import time
from pathlib import Path

import asyncssh

from ..config import BASELINE_DIR, settings
from .. import labinfo
from .driver import lab
from .iosconfig import _GLOBAL, _IF_SUB, _OSPF_SUB, _RMAP_SUB, _SLA_SUB, ConfigSession
from .iosshow import ping as sim_ping, section, traceroute as sim_traceroute
from .render import INVALID

log = logging.getLogger("ospf.sim.ssh")

# -- the exec command tree ------------------------------------------------------------------------------------------
# One command per line; `a|b` = alternatives at that position, <a> = an argument (interface, address, name, number).
_EXEC = """
show running-config
show running-config interface <a>
show startup-config
show interfaces
show interfaces description
show interfaces <a>
show ip interface
show ip interface brief
show ip interface <a>
show ip protocols
show ip protocols summary
show ip route
show ip route ospf|connected|static|local|summary
show ip route vrf <a>
show ip route <a>
show ip route <a> <a>
show ip ospf
show ip ospf neighbor
show ip ospf neighbor detail
show ip ospf neighbor <a>
show ip ospf interface
show ip ospf interface brief
show ip ospf interface <a>
show ip ospf database
show ip ospf database router|network|summary|asbr-summary|external|nssa-external|database-summary
show ip ospf border-routers|statistics|traffic|events|rib|virtual-links|summary-address
show ip sla statistics|summary|configuration
show ip arp
show ip arp vrf <a>
show ip cef
show ip cef <a>
show ip vrf
show ip vrf brief|detail
show ip hosts
show ipv6 ospf
show ipv6 ospf neighbor
show ipv6 ospf neighbor detail
show ipv6 ospf interface
show ipv6 ospf interface brief
show ipv6 ospf database|border-routers
show ipv6 route
show ipv6 route ospf
show ipv6 route <a>
show ipv6 interface brief
show ipv6 protocols
show bfd neighbors
show bfd neighbors details
show cdp
show cdp neighbors
show cdp neighbors detail
show arp|users|history|terminal|privilege|logging|clock|version|inventory|line|snmp|access-lists|standby|track|boot|environment|tech-support|debugging|hosts
show controllers
show controllers <a>
show diag
show processes cpu
show processes cpu sorted|history
show memory
show memory statistics|summary
show flash:|disk0:
show ntp status|associations
show route-map
show route-map <a>
configure terminal
configure
write
write memory
copy running-config startup-config
clear ip ospf process
clear ip ospf <a> process
clear counters
enable|disable|exit|logout|quit|end|help|dir|reload|who
terminal length <a>
terminal width <a>
terminal monitor
terminal no monitor
ping <a>
ping <a> repeat|source|size <a>
ping vrf <a> <a>
ping vrf <a> <a> repeat|source|size <a>
traceroute <a>
traceroute vrf <a> <a>
"""
LEAF = "$"
ARG = "<a>"


def _build(spec: str) -> dict:
    root: dict = {}
    for line in spec.strip().splitlines():
        nodes = [root]
        for tok in line.split():
            nxt = []
            for node in nodes:
                for alt in tok.split("|"):
                    nxt.append(node.setdefault(alt, {}))
            nodes = nxt
        for node in nodes:
            node[LEAF] = True
    return root


TREE = _build(_EXEC)


class ParseError(Exception):
    def __init__(self, kind: str, pos: int = 0, words: list[str] | None = None) -> None:
        super().__init__(kind)
        self.kind, self.pos, self.words = kind, pos, words or []


def parse(line: str, tree: dict = TREE) -> list[str]:
    """Expand IOS abbreviations along the command tree. Raises ParseError(invalid / ambiguous / incomplete)."""
    toks = line.split()
    node, out, col = tree, [], 0
    for k, tok in enumerate(toks):
        col = line.find(tok, col)
        low = tok.lower()
        kws = [w for w in node if w not in (LEAF, ARG)]
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


def help_for(line: str, tree: dict = TREE) -> list[str]:
    """`?`: the words that can follow (`show ?`) or complete the last one (`sh ip o?`)."""
    partial = not line.endswith(" ") and line != ""
    toks = line.split()
    prefix = toks.pop().lower() if partial and toks else ""
    node = tree
    for tok in toks:
        low = tok.lower()
        kws = [w for w in node if w not in (LEAF, ARG)]
        hits = [w for w in kws if w == low] or [w for w in kws if w.startswith(low)]
        if len(hits) == 1:
            node = node[hits[0]]
        elif ARG in node:
            node = node[ARG]
        else:
            return []
    words = sorted(w for w in node if w not in (LEAF, ARG) and w.startswith(prefix))
    if not partial:
        if ARG in node:
            words.append("WORD")
        if LEAF in node:
            words.append("<cr>")
    return words


# configuration keywords: abbreviations expand until the first word that is not one (names, addresses, descriptions)
_CFG_WORDS = ["no", "default", "interface", "router", "ospf", "ipv6", "ip", "network", "area", "hello-interval",
              "dead-interval", "cost", "priority", "network-type", "passive-interface", "shutdown", "address", "mtu",
              "authentication", "authentication-key", "message-digest", "message-digest-key", "stub", "nssa",
              "no-summary", "range", "summary-address", "redistribute", "connected", "static", "subnets",
              "default-information", "originate", "always", "metric", "metric-type", "router-id", "bfd",
              "point-to-point", "broadcast", "non-broadcast", "point-to-multipoint", "translate", "type7", "sla",
              "schedule", "icmp-echo", "frequency", "track", "description", "log-adjacency-changes", "timers",
              "throttle", "spf", "auto-cost", "reference-bandwidth", "max-metric", "router-lsa", "virtual-link",
              "distance", "maximum-paths", "instance", "enable", "unicast-routing", "route-map", "permit", "deny",
              "match", "set", "hostname", "username", "secret", "duplex", "speed", "bandwidth", "logging", "banner",
              "domain", "name", "lookup", "vrf", "forwarding", "line", "vty", "transport", "input", "login", "local",
              "exec-timeout", "service", "cdp", "ntp", "server", "clock", "end", "exit", "do", "access-list"]
_CFG_FIRST = re.compile(r"^(no |default )?(hostname|interface|router|ipv6|ip|route-map|line|enable|username|service|"
                        r"logging|banner|crypto|ntp|snmp-server|access-list|key|boot|track|event|alias|archive|clock|cdp|"
                        r"lldp|aaa|privilege|mpls|bfd|bfd-template|control-plane|vrf|multilink|errdisable|"
                        r"spanning-tree|class-map|policy-map|object-group|license|redundancy|file|exception)( |$)")
_CFG_HELP = """Configure commands:
  hostname <name>        interface <name>        router ospf <pid>        ipv6 router ospf <pid>
  ip route ...           ip sla <n>              route-map <name> ...     username / enable secret
  line vty 0 4           do <exec command>       end (or Ctrl-Z)          exit
Interface: ip address, ip ospf <pid> area <a>, ip ospf hello-interval / dead-interval / cost / priority / network,
  ip mtu, ipv6 address, ipv6 ospf <pid> area <a> [instance n], description, shutdown / no shutdown
Router ospf: router-id, area <a> stub|nssa [no-summary], area <a> nssa translate type7 always,
  redistribute static|connected [metric n] [metric-type 1|2] [subnets], auto-cost reference-bandwidth, passive-interface
"""


def _expand_cfg(line: str) -> str:
    toks = line.split()
    out = []
    for k, tok in enumerate(toks):
        low = tok.lower()
        hits = sorted((w for w in _CFG_WORDS if w.startswith(low)), key=len) if re.fullmatch(r"[a-z-]+", low) else []
        if low in _CFG_WORDS:
            out.append(low)
        elif hits:
            out.append(hits[0])
        else:
            out.extend(toks[k:])
            break
    return " ".join(out)


_PIPES = ["include", "exclude", "begin", "section", "count"]


def _pipe(text: str, spec: str) -> str:
    how, _, pat = spec.strip().partition(" ")
    hits = [p for p in _PIPES if p.startswith(how.lower())] if how else []
    if len(hits) != 1 or (not pat.strip() and hits[0] != "count"):
        return INVALID
    how, pat = hits[0], pat.strip()
    if how == "section":
        return section(text, pat)
    try:
        rx = re.compile(pat or ".")
    except re.error:
        return "% Invalid regular expression\n"
    lines = text.splitlines()
    if how == "include":
        lines = [ln for ln in lines if rx.search(ln)]
    elif how == "exclude":
        lines = [ln for ln in lines if not rx.search(ln)]
    elif how == "begin":
        idx = next((k for k, ln in enumerate(lines) if rx.search(ln)), len(lines))
        lines = lines[idx:]
    elif how == "count":
        return f"Number of lines which match regexp = {sum(1 for ln in lines if rx.search(ln))}\n"
    return "\n".join(lines) + ("\n" if lines else "")


# -- logins -----------------------------------------------------------------------------------------------------------
_USERS = re.compile(r"^username (\S+)(?: privilege (\d+))? (?:secret|password) (?:\d )?(\S+)", re.M)


def logins() -> dict[str, dict]:
    """Router -> {username, password, secret, port, users} for the shared lab (the one the simulator models).
    `users` is every `username` line of the router's baseline (name -> (password, privilege)) plus the inventory login,
    so PuTTY can log in as `cisco` while the automation keeps using `lab`. `username` / `password` are what the PuTTY tab
    shows: OSPF_PUTTY_USER when the router has that user, otherwise the inventory login."""
    rows = labinfo.credentials()[0]["routers"]
    out = {}
    for k, r in enumerate(rows):
        f = BASELINE_DIR / f"{r['name']}.cfg"
        text = f.read_text(encoding="utf-8") if f.is_file() else ""
        users = {u: (pw, int(pr) if pr else 1) for u, pr, pw in _USERS.findall(text)}
        users.setdefault(r["username"], (r["password"], 15))
        shown = settings.putty_user if settings.putty_user in users else r["username"]
        out[r["name"]] = {"username": shown, "password": users[shown][0], "secret": r["secret"], "users": users,
                          "port": settings.sim_ssh_port + k}
    return out


def _live_users(router: str) -> dict:
    """`username` lines typed into the running configuration (in PuTTY) count too."""
    try:
        misc = lab().model.configs[router].misc
    except KeyError:
        return {}
    return {u: (pw, int(pr) if pr else 1) for u, pr, pw in _USERS.findall("\n".join(misc))}


class _Server(asyncssh.SSHServer):
    def __init__(self, router: str, login: dict) -> None:
        self.router, self.login = router, login

    def begin_auth(self, username: str) -> bool:
        return True                                   # always ask for a password

    def password_auth_supported(self) -> bool:
        return True

    def kbdint_auth_supported(self) -> bool:
        return False          # plain password auth: PuTTY shows "cisco@127.0.0.1's password:" as with a real router

    def validate_password(self, username: str, password: str) -> bool:
        users = {**self.login["users"], **_live_users(self.router)}
        ok = username in users and password == users[username][0]
        if not ok:
            log.info("%s: failed SSH login for %r", self.router, username)
        return ok


# -- the shell ----------------------------------------------------------------------------------------------------------
class _Shell:
    def __init__(self, process: asyncssh.SSHServerProcess, router: str, login: dict) -> None:
        self.p, self.router, self.login = process, router, login
        self.user = process.get_extra_info("username") or ""
        peer = process.get_extra_info("peername")
        self.peer = peer[0] if peer else "127.0.0.1"
        users = {**login["users"], **_live_users(router)}
        self.enabled = users.get(self.user, ("", 1))[1] >= 15
        self.mode = None                              # None = exec; otherwise the ConfigSession mode tuple
        self.history: list[str] = []
        self.monitor: asyncio.Task | None = None
        self.since = time.time()
        self.vty = 0
        self.length, self.width = 24, 80

    @property
    def host(self) -> str:
        return lab().model.configs[self.router].hostname

    @property
    def line_name(self) -> str:
        return f"vty{self.vty}"

    def prompt(self) -> str:
        if self.mode is None:
            return f"{self.host}{'#' if self.enabled else '>'}"
        sess = ConfigSession(lab().model.configs[self.router])
        sess.mode = self.mode
        return sess.prompt

    def out(self, text: str) -> None:
        self.p.stdout.write(text)

    def caret(self, line: str, pos: int, kind: str) -> None:
        if kind == "ambiguous":
            self.out(f'% Ambiguous command:  "{line}"\n')
        elif kind == "incomplete":
            self.out("% Incomplete command.\n\n")
        else:
            self.out(" " * (len(self.prompt()) + pos) + "^\n% Invalid input detected at '^' marker.\n\n")

    async def ask(self, question: str, secret: bool = False) -> str | None:
        self.out(question)
        if secret:
            self.p.channel.set_echo(False)
        try:
            line = await self.p.stdin.readline()
        finally:
            if secret:
                self.p.channel.set_echo(True)
                self.out("\n")
        return None if line == "" else line.strip()

    # -- session lifecycle --------------------------------------------------------------------------------------------
    def register(self) -> None:
        sessions = lab().sessions[self.router]
        used = {s["vty"] for s in sessions}
        self.vty = next(k for k in range(16) if k not in used)
        sessions.append({"user": self.user, "vty": self.vty, "peer": self.peer, "since": self.since, "shell": self})

    def unregister(self) -> None:
        sessions = lab().sessions[self.router]
        sessions[:] = [s for s in sessions if s.get("shell") is not self]
        if self.monitor:
            self.monitor.cancel()

    async def run(self) -> None:
        self.out(f"\n{self.host} - Cisco 7206VXR, IOS 15.2(4)S6 (simulated by OSPF SLA & States Executor)\n"
                 f"Type '?' for help.\n\n")
        while True:
            self.out(self.prompt())
            try:
                line = await self.p.stdin.readline()
            except asyncssh.TerminalSizeChanged:
                continue
            except (asyncssh.BreakReceived, asyncssh.SignalReceived):   # Ctrl-C / Ctrl-Z: back to exec mode, as IOS
                if self.mode is not None:
                    self.out("^Z\n")
                    self.mode = None
                    await asyncio.to_thread(lab().config_done, self.router, self.user, self.line_name, self.peer)
                else:
                    self.out("\n")
                continue
            if line == "":                            # client closed the channel
                return
            if await self.handle(line.rstrip("\r\n")) is False:
                return

    # -- exec mode ------------------------------------------------------------------------------------------------------
    async def handle(self, line: str) -> bool:
        if not line.strip():
            return True
        if self.mode is not None:
            return await self.config_line(line.strip())
        if line.rstrip().endswith("?"):
            words = help_for(line.rstrip()[:-1])
            self.out(_columns(words) if words else "% Unrecognized command\n")
            return True
        self.history.append(line.strip())
        body, bar, pipe = line.partition("|")
        try:
            words = parse(body)
        except ParseError as e:
            self.caret(body.strip(), e.pos - (len(body) - len(body.lstrip())), e.kind)
            return True
        cmd = " ".join(words)
        verb = words[0]
        if not self.enabled and verb not in ("show", "enable", "exit", "logout", "quit", "ping", "traceroute",
                                              "terminal", "help", "who"):
            self.caret(body.strip(), 0, "invalid")
            return True
        if verb == "show":
            text = await self.show(cmd)
            if bar:
                text = _pipe(text, pipe)
            self.out(text if text.endswith("\n") or not text else text + "\n")
        elif verb in ("exit", "logout", "quit"):
            return False
        elif verb == "help":
            self.out("Help may be requested at any point in a command by entering a question mark '?'.\n"
                     "Abbreviations work while they stay unique: sh ip int br, sh ip ospf nei, conf t, wr.\n")
        elif verb == "enable":
            if not self.enabled:
                pw = await self.ask("Password: ", secret=True)
                if pw == self.login["secret"]:
                    self.enabled = True
                else:
                    self.out("% Access denied\n\n")
        elif verb == "disable":
            self.enabled = False
        elif verb == "end":
            pass
        elif verb == "terminal":
            await self.terminal(words[1:])
        elif verb == "configure":
            self.out("Enter configuration commands, one per line.  End with CNTL/Z.\n")
            self.mode = ("global",)
        elif cmd in ("write", "write memory"):
            self.out("Building configuration...\n")
            await asyncio.to_thread(lab().write_mem, self.router)
            self.out("[OK]\n")
        elif verb == "copy":
            ans = await self.ask("Destination filename [startup-config]? ")
            if ans is None:
                return False
            self.out("Building configuration...\n")
            await asyncio.to_thread(lab().write_mem, self.router)
            self.out("[OK]\n")
        elif cmd.startswith("clear ip ospf"):
            ans = await self.ask("Reset ALL OSPF processes? [no]: ")
            if ans and ans.lower() in ("y", "yes"):
                await asyncio.to_thread(lab().exec_cmd, self.router, "clear ip ospf process")
        elif cmd == "clear counters":
            await self.ask('Clear "show interface" counters on all interfaces [confirm]')
        elif verb == "reload":
            self.out("% Reload is not available on a simulated router: use Reset lab to baseline on the dashboard.\n")
        elif verb == "who":
            self.out(self.users())
        elif verb == "dir":
            self.out(await asyncio.to_thread(lab().show, self.router, "dir"))
        elif verb in ("ping", "traceroute"):
            self.out(await asyncio.to_thread(self.reach, verb, words[1:]))
        return True

    async def terminal(self, args: list[str]) -> None:
        if args[:1] == ["length"]:
            self.length = int(args[1]) if args[1].isdigit() else self.length
        elif args[:1] == ["width"]:
            self.width = int(args[1]) if args[1].isdigit() else self.width
        elif args == ["monitor"]:
            if not self.monitor or self.monitor.done():
                self.monitor = asyncio.create_task(self._follow_logs())
        elif args == ["no", "monitor"] and self.monitor:
            self.monitor.cancel()
            self.monitor = None

    async def _follow_logs(self) -> None:
        seq = lab().log_seq
        while True:
            await asyncio.sleep(1)
            seq, lines = await asyncio.to_thread(lab().since, self.router, seq)
            for ln in lines:
                self.out(f"\n{ln}\n")

    async def show(self, cmd: str) -> str:
        if cmd in ("show users",):
            return self.users()
        if cmd == "show history":
            return "".join(f"  {h}\n" for h in self.history[-20:])
        if cmd == "show terminal":
            return (f"Line {self.vty + 2}, Location: \"\", Type: \"xterm\"\nLength: {self.length} lines, Width: "
                    f"{self.width} columns\nBaud rate (TX/RX) is 9600/9600\nStatus: PSI Enabled, Ready, Active, No Exit Banner\n"
                    "Capabilities: none\nModem state: Ready\nSession limit is not set.\nTime since activation: "
                    f"{_hms(time.time() - self.since)}\nEditing is enabled.\nHistory is enabled, history size is 20.\n"
                    "Allowed input transports are ssh.\nAllowed output transports are telnet ssh.\n")
        return await asyncio.to_thread(lab().show, self.router, cmd)

    def users(self) -> str:
        rows = ["    Line       User       Host(s)              Idle       Location"]
        for s in sorted(lab().sessions[self.router], key=lambda s: s["vty"]):
            me = "*" if s.get("shell") is self else " "
            rows.append(f"{me}{s['vty'] + 2:>3} vty {s['vty']:<5} {s['user']:<10} idle                 "
                        f"{_hms(time.time() - s['since'])} {s['peer']}")
        rows += ["", "  Interface    User               Mode         Idle     Peer Address", ""]
        return "\n".join(rows)

    def reach(self, verb: str, args: list[str]) -> str:
        vrf = None
        if args[:1] == ["vrf"]:
            vrf, args = args[1], args[2:]
        dest = args[0] if args else ""
        repeat = 5
        if "repeat" in args:
            try:
                repeat = max(1, min(int(args[args.index("repeat") + 1]), 100))
            except (IndexError, ValueError):
                pass
        if vrf:
            return _vrf_reach(self.router, vrf, dest, verb, repeat)
        snap = lab().snapshot()
        if verb == "ping":
            return sim_ping(lab().model, snap, self.router, dest, repeat)
        return sim_traceroute(lab().model, snap, self.router, dest)

    # -- configuration mode ---------------------------------------------------------------------------------------------
    async def config_line(self, line: str) -> bool:
        if line.endswith("?"):
            self.out(_CFG_HELP)
            return True
        self.history.append(line)
        try:
            as_exec = " ".join(parse(line.partition("|")[0]))
        except ParseError:
            as_exec = ""
        if as_exec.startswith("show ") or as_exec in ("write", "write memory"):
            line = "do " + line                       # forgiving: `sh ip ospf nei` without `do` (a bare `sh` = shutdown)
        elif not line.lower().startswith("do "):
            line = _expand_cfg(line)
        low = line.lower()
        if low == "end":
            self.mode = None
            await asyncio.to_thread(lab().config_done, self.router, self.user, self.line_name, self.peer)
            return True
        if low == "exit":
            if self.mode[0] != "global":
                self.mode = ("global",)
            else:
                self.mode = None
                await asyncio.to_thread(lab().config_done, self.router, self.user, self.line_name, self.peer)
            return True
        if low.startswith("do "):
            saved, self.mode = self.mode, None
            await self.handle(line[3:].strip())
            self.mode = saved
            return True
        if not self._valid_cfg(low):
            self.caret(line, 0, "invalid")
            return True
        self.mode = await asyncio.to_thread(lab().config_line, self.router, self.mode, line)
        return True

    def _valid_cfg(self, low: str) -> bool:
        kind = self.mode[0]
        sub = {"if": _IF_SUB, "ospf": _OSPF_SUB, "ospf6": _OSPF_SUB, "rmap": _RMAP_SUB, "sla": _SLA_SUB}.get(kind)
        if kind == "other":
            return True
        if sub is not None and sub.match(low):
            return True
        if kind == "if" and re.match(r"^(no |default )?(duplex|speed|bandwidth|delay|mtu|keepalive|load-interval|cdp|"
                                     r"description|shutdown|negotiation|media-type)( |$)", low):
            return True
        return bool(_GLOBAL.match(low) or _CFG_FIRST.match(low))


def _columns(words: list[str]) -> str:
    return "".join(f"  {w}\n" for w in words)


def _hms(sec: float) -> str:
    s = int(sec)
    return f"{s // 3600:02d}:{(s // 60) % 60:02d}:{s % 60:02d}"


def _vrf_reach(router: str, vrf: str, dest: str, verb: str, repeat: int) -> str:
    """The management VRF: the other routers' Fa0/0 and the gateway answer."""
    cfg = lab().model.configs[router]
    up = set()
    for r, c in lab().model.configs.items():
        for i in c.ifaces.values():
            if i.vrf == vrf and i.ip and not i.shutdown:
                up.add(i.ip)
    up |= {s[2] for s in cfg.statics if s[3] == vrf}
    try:
        ipaddress.ip_address(dest)
    except ValueError:
        return "% Unrecognized host or address, or protocol not running.\n"
    ok = dest in up
    if verb == "traceroute":
        return (f"Type escape sequence to abort.\nTracing the route to {dest}\nVRF info: (vrf in name/id, vrf out name/id)\n"
                + (f"  1 {dest} 4 msec 3 msec 4 msec\n" if ok else "  1  *  *  * \n  2  *  *  * \n"))
    marks = ("!" if ok else ".") * repeat
    tail = (f"Success rate is 100 percent ({repeat}/{repeat}), round-trip min/avg/max = 1/3/8 ms" if ok
            else f"Success rate is 0 percent (0/{repeat})")
    return (f"Type escape sequence to abort.\nSending {repeat}, 100-byte ICMP Echos to {dest}, timeout is 2 seconds:\n"
            f"{marks}\n{tail}\n")


async def _session(process: asyncssh.SSHServerProcess, router: str, login: dict) -> None:
    sh = _Shell(process, router, login)
    try:
        process.channel.register_key("\x1a", lambda _line, _pos: ("TSTP", -1))   # Ctrl-Z
    except (AssertionError, AttributeError):          # no pty / no line editor (an exec request)
        pass
    sh.register()
    try:
        if process.command:                           # `plink ... "show ip ospf neighbor"`: one command, no prompt
            sh.enabled = True
            for part in process.command.split(";"):
                await sh.handle(part.strip())
        else:
            await sh.run()
    except Exception:                                  # noqa: BLE001 - never take the server down with one session
        log.exception("%s: SSH session failed", router)
    finally:
        sh.unregister()
        process.exit(0)


_KEY: asyncssh.SSHKey | None = None


def _host_key() -> asyncssh.SSHKey:
    """An RSA host key, kept on disk so it survives restarts. RSA because putty-setup.ps1 can then store it in PuTTY's
    trusted keys up front (PuTTY keeps an RSA key as plain exponent,modulus), so no host-key alert interrupts the login."""
    global _KEY
    if _KEY is not None:
        return _KEY
    path = Path(settings.sim_ssh_hostkey)
    if path.is_file():
        try:
            key = asyncssh.read_private_key(str(path))
            if key.algorithm == b"ssh-rsa":
                _KEY = key
                return key
        except (OSError, asyncssh.KeyImportError):
            pass
    key = asyncssh.generate_private_key("ssh-rsa", key_size=2048)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        key.write_private_key(str(path))
    except OSError:
        log.warning("could not save the SSH host key to %s; a new one is made on every start", path)
    _KEY = key
    return key


def putty_hostkey() -> str:
    """The host key in PuTTY's registry format (SshHostKeys value for "rsa2@<port>:<host>"): 0x<e>,0x<n>."""
    from cryptography.hazmat.primitives.serialization import load_ssh_public_key
    nums = load_ssh_public_key(_host_key().export_public_key("openssh")).public_numbers()
    return f"0x{nums.e:x},0x{nums.n:x}"


async def start() -> list:
    """Start one SSH server per simulated router. Returns the servers (close them on shutdown)."""
    key = _host_key()
    servers = []
    for router, login in logins().items():
        try:
            srv = await asyncssh.create_server(
                lambda r=router, lg=login: _Server(r, lg), settings.sim_ssh_bind, login["port"],
                server_host_keys=[key], line_editor=True, encoding="utf-8",
                process_factory=lambda p, r=router, lg=login: _session(p, r, lg))
            servers.append(srv)
            log.info("%s: SSH on %s:%s", router, settings.sim_ssh_bind, login["port"])
        except OSError as exc:
            log.error("%s: cannot listen on port %s (%s)", router, login["port"], exc)
    return servers


def fingerprint() -> str:
    try:
        return _host_key().get_fingerprint("sha256")
    except Exception:                                  # noqa: BLE001
        return ""
