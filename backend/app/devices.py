"""Router access. Real mode: Netmiko SSH to the MGMT VRF address, falling back to the EVE-NG telnet console port if SSH
is unreachable. Simulation mode (OSPF_SIMULATE=true): the in-process model in app/sim/.

Every real session checks the router's hostname before it sends anything (OSPF_HOSTNAME_GUARD), retries a refused or
timed-out connection (OSPF_CONNECT_RETRIES), and push_config reports any line IOS rejected."""
from __future__ import annotations

import re
import time

from .config import settings
from .inventory import Device

_IOS_ERROR = re.compile(r"^% ?(Invalid input|Incomplete command|Ambiguous command|Unknown command)[^\n]*", re.M)


class HostnameMismatch(RuntimeError):
    pass


def _sim():
    from .sim.driver import lab
    return lab()


def _ssh_params(dev: Device) -> dict:
    return dict(
        device_type="cisco_ios",
        host=dev.mgmt_ip,
        username=dev.username,
        password=dev.password,
        secret=dev.secret,
        fast_cli=False,
        conn_timeout=settings.conn_timeout,
    )


def _console_params(dev: Device) -> dict:
    return dict(
        device_type="cisco_ios_telnet",
        host=dev.console_host,
        port=dev.console_port,
        username=dev.username,
        password=dev.password,
        secret=dev.secret,
        fast_cli=False,
        conn_timeout=settings.conn_timeout,
    )


def retry(fn, attempts: int, delay: float = 2.0, retry_on: tuple = (Exception,)):
    """Call fn(); on one of `retry_on`, wait and try again, up to `attempts` calls in total. Re-raises the last error."""
    last = None
    for k in range(max(1, attempts)):
        try:
            return fn()
        except retry_on as exc:  # noqa: PERF203
            last = exc
            if k + 1 < attempts:
                time.sleep(delay * (k + 1))
    raise last


def check_hostname(dev: Device, prompt: str) -> None:
    """The prompt (R4#, R4>, R4(config)#) must start with the inventory name, case-insensitive."""
    host = re.split(r"[#>(]", prompt.strip(), maxsplit=1)[0]
    if settings.hostname_guard and host.lower() != dev.name.lower():
        raise HostnameMismatch(
            f"hostname guard: {dev.mgmt_ip} answered as '{host}', expected '{dev.name}' - nothing was sent "
            "(check the inventory address, or set OSPF_HOSTNAME_GUARD=false before the first bootstrap)")


def _connect(dev: Device):
    from netmiko import ConnectHandler
    from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

    def ssh():
        return ConnectHandler(**_ssh_params(dev))

    try:
        conn = retry(ssh, settings.connect_retries, retry_on=(NetmikoTimeoutException, OSError))
    except (NetmikoTimeoutException, NetmikoAuthenticationException, OSError):
        if settings.console_fallback and dev.console:
            conn = ConnectHandler(**_console_params(dev))
        else:
            raise
    try:
        check_hostname(dev, conn.find_prompt())
    except Exception:
        conn.disconnect()
        raise
    return conn


def show(dev: Device, command: str, use_textfsm: bool = False) -> str:
    if settings.simulate:
        return _sim().show(dev.name, command)
    with _connect(dev) as c:
        c.enable()
        return c.send_command(command, use_textfsm=use_textfsm, read_timeout=settings.read_timeout)


def show_many(dev: Device, commands: list[str]) -> list[str]:
    """Several read-only commands in one SSH session (the monitor's poll: one login per router instead of one per command)."""
    if settings.simulate:
        return [_sim().show(dev.name, cmd) for cmd in commands]
    with _connect(dev) as c:
        c.enable()
        return [c.send_command(cmd, read_timeout=settings.read_timeout) for cmd in commands]


def exec_cmd(dev: Device, command: str) -> str:
    """Exec-mode command; answers IOS confirmation prompts (e.g. `clear ip ospf process`)."""
    if settings.simulate:
        return _sim().exec_cmd(dev.name, command)
    with _connect(dev) as c:
        c.enable()
        out = c.send_command_timing(command, read_timeout=settings.read_timeout)
        if out.rstrip().endswith(("[no]:", "[confirm]", "[yes/no]:")):
            out += c.send_command_timing("yes" if "no]" in out[-12:] else "\n")
        return out


def ios_errors(output: str) -> list[str]:
    """Lines IOS rejected, with the command echoed just before each error."""
    lines = output.splitlines()
    errs = []
    for k, ln in enumerate(lines):
        if _IOS_ERROR.match(ln.strip()):
            prev = next((lines[j].strip() for j in range(k - 1, -1, -1) if lines[j].strip() and "^" not in lines[j]), "")
            errs.append(f"{prev}  ->  {ln.strip()}")
    return errs


def push_config(dev: Device, lines: list[str], save: bool = True) -> str:
    lines = [ln for ln in lines if ln.strip() and not ln.strip().startswith("!")]
    if settings.simulate:
        return _sim().push(dev.name, lines, save)
    with _connect(dev) as c:
        c.enable()
        out = c.send_config_set(lines, read_timeout=max(60, settings.read_timeout))
        errs = ios_errors(out)
        if save:
            out += "\n" + c.save_config()
        if errs:
            out += "\nWARNING: IOS rejected " + str(len(errs)) + " line(s):\n" + "\n".join(f"  {e}" for e in errs)
        return out


def push_file(dev: Device, path: str) -> str:
    if settings.simulate:
        from .sim.driver import is_baseline
        if is_baseline(dev.name, path):
            return _sim().reset(dev.name)
    with open(path, encoding="utf-8") as fh:
        return push_config(dev, fh.read().splitlines())
