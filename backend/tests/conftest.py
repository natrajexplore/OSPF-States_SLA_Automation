"""Offline tests: the backend in simulation mode, no EVE-NG, no SSH, no Kafka."""
import os
import sys
from pathlib import Path

os.environ.setdefault("OSPF_SIMULATE", "true")
os.environ.setdefault("OSPF_SIM_CONVERGE", "0")        # adjacencies form instantly: tests check outcomes, not timing
os.environ.setdefault("OSPF_SIM_SETTLE_SCALE", "0")
os.environ.setdefault("OSPF_MONITOR", "false")
os.environ.setdefault("OSPF_KAFKA_BOOTSTRAP", "")
os.environ.setdefault("OSPF_SIM_SSH", "false")          # test_sim_ssh.py starts its own servers on free ports
os.environ.setdefault("OSPF_RUNS", str(Path(__file__).resolve().parent / ".runs"))

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
