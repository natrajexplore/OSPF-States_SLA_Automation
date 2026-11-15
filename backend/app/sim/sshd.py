"""SSH login to the simulated routers, so PuTTY (or any SSH client) can open R1..R4 in simulation mode.

One SSH server per router of the inventory, on consecutive ports from OSPF_SIM_SSH_PORT (R1 2201, R2 2202, ...). Login
with the router's inventory username and password; the shell is a small IOS exec / configure-terminal CLI on top of the
same SimLab the dashboard uses, so a change typed in PuTTY shows up in the 3D view, the monitor and Grafana, and the
dashboard's Apply / Rollback shows up in PuTTY.
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

import asyncssh

from ..config import BASELINE_DIR, settings
from .. import labinfo
from .driver import lab
from .iosconfig import ConfigSession
from .render import INVALID

log = logging.getLogger("ospf.sim.ssh")

# words an IOS abbreviation can expand to ("sh ip ospf nei" -> "show ip ospf neighbor"); the shortest match wins
_WORDS = ["show", "ip", "ipv6", "ospf", "neighbor", "neighbors", "detail", "details", "interface", "brief", "database",
          "border-routers", "route", "router", "running-config", "section", "bfd", "sla", "statistics", "clock",
          "version", "configure", "terminal", "length", "width", "write", "memory", "clear", "process", "enable",
          "disable", "exit", "logout", "quit", "end", "copy", "startup-config", "include", "exclude", "begin", "ping",
          "help", "history"]
# configuration keywords; expansion stops at the first word that is not one (names, addresses, descriptions)
_CFG_WORDS = ["no", "default", "interface", "router", "ospf", "ipv6", "ip", "network", "area", "hello-interval",
              "dead-interval", "cost", "priority", "network-type", "passive-interface", "shutdown", "address", "mtu",
              "authentication", "authentication-key", "message-digest", "message-digest-key", "stub", "nssa",
              "no-summary", "range", "summary-address", "redistribute", "connected", "static", "subnets",
              "default-information", "originate", "always", "metric", "metric-type", "router-id", "bfd",
              "point-to-point", "broadcast", "non-broadcast", "point-to-multipoint", "translate", "type7", "sla",
              "schedule", "icmp-echo", "frequency", "track", "description", "log-adjacency-changes", "timers",
              "throttle", "spf", "auto-cost", "reference-bandwidth", "max-metric", "router-lsa", "virtual-link",
              "distance", "maximum-paths", "instance", "enable", "unicast-routing", "route-map", "permit", "deny",
              "match", "set", "hostname"]
_PIPE = {"include": "include", "exclude": "exclude", "begin": "begin", "section": "section"}
_HELP = """Exec commands:
  show ip ospf [neighbor [detail] | interface [brief] | database | border-routers]
  show ip route [ospf | <address>]       show ip interface brief
  show ipv6 ospf [neighbor | interface brief]   show ipv6 route [ospf]
  show bfd neighbors   show ip sla statistics   show clock   show version
  show running-config | section [ipv6] router ospf
  configure terminal   write memory   clear ip ospf process
  enable   disable   terminal length 0   exit
  Any show command takes  | include <regex>,  | exclude <regex>  or  | begin <regex>.
"""


def _expand(line: str, words: list[str] = _WORDS, stop: bool = False) -> str:
    """IOS-style abbreviations: each word becomes the shortest keyword it starts. With stop=True (configuration
    lines) expansion ends at the first word that is no keyword, so names and descriptions are left alone."""
    toks = line.split()
    out = []
    for k, tok in enumerate(toks):
        low = tok.lower()
        hits = sorted((w for w in words if w.startswith(low)), key=len) if re.fullmatch(r"[a-z-]+", low) else []
        if low in words:
            out.append(low)
        elif hits:
            out.append(hits[0])
        elif stop:
            out.extend(toks[k:])
            break
        else:
            out.append(tok)
    return " ".join(out)


def _filter(text: str, how: str, pattern: str) -> str:
    try:
        rx = re.compile(pattern)
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
    return "\n".join(lines) + ("\n" if lines else "")


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
        ok = username in self.login["users"] and password == self.login["users"][username][0]
        if not ok:
            log.info("%s: failed SSH login for %r", self.router, username)
        return ok


class _Shell:
    def __init__(self, process: asyncssh.SSHServerProcess, router: str, login: dict) -> None:
        self.p, self.router, self.login = process, router, login
        user = process.get_extra_info("username") or ""
        self.enabled = login["users"].get(user, ("", 1))[1] >= 15
        self.mode = None                              # None = exec; otherwise the ConfigSession mode tuple

    @property
    def host(self) -> str:
        return lab().model.configs[self.router].hostname

    def prompt(self) -> str:
        if self.mode is None:
            return f"{self.host}{'#' if self.enabled else '>'}"
        sess = ConfigSession(lab().model.configs[self.router])
        sess.mode = self.mode
        return sess.prompt

    def out(self, text: str) -> None:
        self.p.stdout.write(text)

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

    async def run(self) -> None:
        self.out(f"\n{self.router} - simulated Cisco 7206VXR, IOS 15.2 (OSPF SLA & States Executor)\n"
                 f"Type '?' for the commands this simulator knows.\n\n")
        while True:
            self.out(self.prompt())
            try:
                line = await self.p.stdin.readline()
            except asyncssh.TerminalSizeChanged:
                continue
            except (asyncssh.BreakReceived, asyncssh.SignalReceived):   # Ctrl-C / Ctrl-Z: back to exec mode, as IOS
                self.out("^Z\n" if self.mode is not None else "\n")
                self.mode = None
                continue
            if line == "":                            # client closed the channel
                return
            if await self.handle(line.strip()) is False:
                return

    async def handle(self, line: str) -> bool:
        if not line:
            return True
        if self.mode is not None:
            return await self.config_line(line)
        cmd = _expand(line)
        low = cmd.lower()
        if low in ("?", "help"):
            self.out(_HELP)
        elif low in ("exit", "logout", "quit"):
            return False
        elif low == "enable":
            if not self.enabled:
                pw = await self.ask("Password: ", secret=True)
                if pw == self.login["secret"]:
                    self.enabled = True
                else:
                    self.out("% Access denied\n\n")
        elif low == "disable":
            self.enabled = False
        elif low.startswith("terminal "):
            pass
        elif not self.enabled and not low.startswith("show "):
            self.out(f"{INVALID}")
        elif low.startswith("show "):
            self.out(await self.show(cmd))
        elif low in ("configure terminal", "configure", "conf t"):
            self.out("Enter configuration commands, one per line.  End with CNTL/Z.\n")
            self.mode = ("global",)
        elif low in ("write", "write memory", "copy running-config startup-config"):
            self.out("Building configuration...\n[OK]\n")
        elif re.fullmatch(r"clear ipv?6? ?ospf (?:\d+ )?process", low):
            ans = await self.ask("Reset ALL OSPF processes? [no]: ")
            if ans and ans.lower() in ("y", "yes"):
                await asyncio.to_thread(lab().exec_cmd, self.router, "clear ip ospf process")
        elif low.startswith("ping"):
            self.out("% ping is not modelled by the simulator: use show ip route / show ip ospf neighbor\n")
        else:
            self.out(f"{' ' * (len(self.prompt()) + len(line.split()[0]))}^\n{INVALID}")
        return True

    async def show(self, cmd: str) -> str:
        body, _, pipe = cmd.partition("|")
        body = body.strip()
        pipe = pipe.strip()
        text = await asyncio.to_thread(lab().show, self.router, cmd if pipe.startswith("section") else body)
        if pipe and not pipe.startswith("section"):
            how, _, pat = pipe.partition(" ")
            how = _PIPE.get(how)
            if not how or not pat:
                return INVALID
            text = _filter(text, how, pat.strip())
        return text if text.endswith("\n") else text + "\n"

    async def config_line(self, line: str) -> bool:
        as_exec = _expand(line)
        if as_exec.lower().startswith("show ") or as_exec.lower() in ("write", "write memory"):
            line = "do " + line                       # forgiving: `sh ip ospf nei` without `do` (a bare `sh` = shutdown)
        else:
            line = _expand(line, _CFG_WORDS, stop=True)
        low = line.lower()
        if low == "end":
            self.mode = None
            return True
        if low == "exit":
            self.mode = ("global",) if self.mode[0] != "global" else None
            return True
        if low.startswith("do "):
            saved, self.mode = self.mode, None
            await self.handle(line[3:].strip())
            self.mode = saved
            return True
        self.mode = await asyncio.to_thread(lab().config_line, self.router, self.mode, line)
        return True


async def _session(process: asyncssh.SSHServerProcess, router: str, login: dict) -> None:
    sh = _Shell(process, router, login)
    try:
        process.channel.register_key("\x1a", lambda _line, _pos: ("TSTP", -1))   # Ctrl-Z
    except (AssertionError, AttributeError):          # no pty / no line editor (an exec request)
        pass
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
