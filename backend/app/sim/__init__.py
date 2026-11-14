"""Simulation mode (OSPF_SIMULATE=true): an in-process model of the lab's Cisco IOS routers.

The model is driven by the same configuration the real routers receive: baseline/*.cfg at start, then every line a
scenario pushes. From that configuration it computes OSPFv2 and OSPFv3 adjacencies (hello/dead, area, stub flags,
network type, MTU, instance ID), DR/BDR election, the LSDB, SPF (intra-area, inter-area, E2, NSSA N2 with translator
election), BFD sessions and IP SLA, and answers `show` commands in IOS format. Nothing here talks to a network.

It exists so the dashboard can be run, demonstrated and tested on any PC without EVE-NG. It is a model, not an IOS
emulator: timers are compressed and only the commands the scenarios and the dashboard use are understood.
"""
