"""SSH login to the simulated routers (app/sim/sshd.py): what PuTTY does, driven with an asyncssh client."""
import asyncio
import socket

import asyncssh
import pytest

from app.config import settings
from app.sim import sshd
from app.sim.driver import lab


def _free_base(n: int = 4) -> int:
    for base in range(24000, 30000, 10):
        socks = []
        try:
            for k in range(n):
                s = socket.socket()
                s.bind(("127.0.0.1", base + k))
                socks.append(s)
            return base
        except OSError:
            continue
        finally:
            for s in socks:
                s.close()
    raise RuntimeError("no free ports")


@pytest.fixture()
def servers(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "sim_ssh_port", _free_base())
    monkeypatch.setattr(settings, "sim_ssh_bind", "127.0.0.1")
    monkeypatch.setattr(settings, "sim_ssh_hostkey", str(tmp_path / "hostkey"))
    lab().reset_all()
    yield settings.sim_ssh_port


def _connect(port, password="lab123"):
    return asyncssh.connect("127.0.0.1", port, username="lab", password=password, known_hosts=None,
                            client_keys=None, preferred_auth="password,keyboard-interactive")


async def _with_servers(fn):
    srvs = await sshd.start()
    try:
        return await fn()
    finally:
        for s in srvs:
            s.close()


def test_logins_follow_inventory_order(servers):
    lg = sshd.logins()
    assert [lg[r]["port"] for r in ("R1", "R2", "R3", "R4")] == [servers + k for k in range(4)]
    assert lg["R1"]["username"] == "lab" and lg["R1"]["privilege"] == 15


def test_exec_command_and_bad_password(servers):
    async def run():
        async with _connect(servers + 2) as conn:                       # R3
            res = await conn.run("sh ip ospf nei")
            assert "FULL" in res.stdout and "10.255.0.4" in res.stdout
        with pytest.raises(asyncssh.PermissionDenied):
            async with _connect(servers, password="wrong"):
                pass
    asyncio.run(_with_servers(run))


def test_interactive_config_changes_the_lab(servers):
    async def run():
        async with _connect(servers + 2) as conn:
            proc = await conn.create_process(term_type="xterm")

            async def until(text, timeout=5.0):
                buf = ""
                while text not in buf:
                    buf += await asyncio.wait_for(proc.stdout.read(4096), timeout)
                return buf

            await until("R3#")
            for line in ["conf t", "int e1/1", "ip ospf hello 5"]:
                proc.stdin.write(line + "\r")
                await until("#")
            proc.stdin.write("\x1a")                                    # Ctrl-Z
            await until("R3#")
            assert lab().model.configs["R3"].ifaces["Ethernet1/1"].hello == 5
            proc.stdin.write("sh ip ospf int e1/1 | inc Hello\r")
            assert "Hello 5" in await until("R3#")
            proc.stdin.write("exit\r")
            await proc.wait_closed()
    asyncio.run(_with_servers(run))
