"""Physical D1-P topology definitions.

This module does not communicate with hardware. It encodes the evidence rule
that physical authority count is based on distinct authority/compute domains,
not the number of processors/cores present on a board. Power-domain independence
is a separate property and is only required for power-loss resilience claims.

The Arduino UNO Q is therefore one physical node even though it contains:
- Qualcomm Dragonwing QRB2210 MPU running Debian Linux
- STM32U585 MCU running Arduino Core on Zephyr

For the planned D1-P profile the STM32U585 is the deterministic authority
domain. The QRB2210 Linux domain is the transport/recovery/self-healing service
plane and has zero authority to manufacture votes or commits.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class PhysicalAuthorityNode:
    node_id: str
    board_model: str
    transport: str
    endpoint: str
    authority_domain: str
    service_domains: tuple[str, ...]
    failure_domain: str
    physically_distinct: bool = True


@dataclass(frozen=True)
class PhysicalTopologyAssessment:
    physical_nodes: int
    independent_failure_domains: int
    authority_domains: int
    pair_qualification_ready: bool
    two_of_three_quorum_ready: bool
    reasons: tuple[str, ...]


def assess_topology(nodes: Iterable[PhysicalAuthorityNode]) -> PhysicalTopologyAssessment:
    nodes = tuple(nodes)
    failures = {node.failure_domain for node in nodes if node.physically_distinct}
    authority_domains = {f"{node.failure_domain}:{node.authority_domain}" for node in nodes}

    pair_ready = len(failures) >= 2
    quorum_ready = len(failures) >= 3

    reasons: list[str] = []
    if pair_ready:
        reasons.append("at least two distinct physical authority/compute domains are present")
    else:
        reasons.append("fewer than two distinct physical authority/compute domains are present")

    if quorum_ready:
        reasons.append("2-of-3 physical quorum can be qualified")
    else:
        reasons.append(
            "2-of-3 physical quorum is not yet qualified; three distinct physical authority/compute domains are required"
        )

    return PhysicalTopologyAssessment(
        physical_nodes=len(nodes),
        independent_failure_domains=len(failures),
        authority_domains=len(authority_domains),
        pair_qualification_ready=pair_ready,
        two_of_three_quorum_ready=quorum_ready,
        reasons=tuple(reasons),
    )


def current_local_profile() -> tuple[PhysicalAuthorityNode, ...]:
    return (
        PhysicalAuthorityNode(
            node_id="A",
            board_model="ESP32-S3",
            transport="USB Serial/JTAG",
            endpoint="COM10",
            authority_domain="ESP32-S3 deterministic authority task",
            service_domains=(),
            failure_domain="esp32-s3-com10",
        ),
        PhysicalAuthorityNode(
            node_id="B",
            board_model="Arduino UNO Q",
            transport="USB-C / board connection (COM5 endpoint to be locally identified)",
            endpoint="COM5",
            authority_domain="STM32U585 Cortex-M33 / Zephyr deterministic authority",
            service_domains=(
                "Qualcomm Dragonwing QRB2210 Debian transport plane",
                "Arduino Bridge/RPC service plane",
                "self-healing/recovery supervisor",
            ),
            failure_domain="arduino-uno-q-com5",
        ),
    )


def tri_heterogeneous_profile() -> tuple[PhysicalAuthorityNode, ...]:
    """Tri-architecture heterogeneous physical cluster (D1-P3).

    Three distinct physical authority/compute domains:
      - Node A: ESP32-S3 (Xtensa LX7)
      - Node B: Arduino UNO Q (ARM Cortex-M33 + QRB2210 Linux service plane)
      - Node C: Laptop CPU Host (x86-64 isolated authority service)

    Deployment note: the laptop currently supplies USB power to Nodes A and B.
    The three authority domains are distinct, but the topology has a shared
    upstream laptop power dependency.
    """
    return (
        PhysicalAuthorityNode(
            node_id="A",
            board_model="ESP32-S3",
            transport="USB Serial/JTAG",
            endpoint="COM10",
            authority_domain="ESP32-S3 Xtensa LX7 deterministic authority task",
            service_domains=(),
            failure_domain="esp32-s3-com10",
        ),
        PhysicalAuthorityNode(
            node_id="B",
            board_model="Arduino UNO Q",
            transport="USB Serial gadget / CDC-ACM",
            endpoint="COM5",
            authority_domain="STM32U585 Cortex-M33 / Zephyr deterministic authority",
            service_domains=(
                "Qualcomm Dragonwing QRB2210 Debian transport plane",
                "Arduino Bridge/RPC service plane",
                "self-healing/recovery supervisor",
            ),
            failure_domain="arduino-uno-q-com5",
        ),
        PhysicalAuthorityNode(
            node_id="C",
            board_model="Laptop CPU Host",
            transport="Loopback TCP Socket",
            endpoint="127.0.0.1:9527",
            authority_domain="Laptop x86-64 isolated authority service",
            service_domains=(
                "Standalone OS process",
                "Isolated persistent storage",
            ),
            failure_domain="laptop-cpu-host",
        ),
    )


if __name__ == "__main__":
    assessment = assess_topology(tri_heterogeneous_profile())
    print(assessment)
