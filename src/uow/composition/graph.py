"""Realization Graph definitions for Campaign A2: Adaptive Composition Runtime.

The Realization Graph G defines HOW work is accomplished:
- Computational and operational nodes (actors, accelerators, microcontrollers, verifiers)
- Causal and dataflow dependency edges
- Substrate, authority tier, and failure annotations
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from ..state import canonical_json


@dataclass(frozen=True)
class RealizationNode:
    """Individual computational actor or operational step in realization graph G."""
    node_id: str
    role: str  # Semantic role: e.g. "parser", "worker", "resolver", "verifier", "commit", "authority"
    actor_class: str = "cpu"  # "cpu", "npu", "gpu", "remote", "physical_esp32", "physical_unoq"
    authority_tier: str = "untrusted"  # "untrusted", "verifier", "authority_quorum", "deterministic_judge"
    inputs: Tuple[str, ...] = ()
    outputs: Tuple[str, ...] = ()
    generates_provenance: bool = True
    evidence_level: str = "portable"  # "portable" or "physical"
    duration_ms: float = 10.0
    cpu_cores: int = 1
    ram_units: int = 2
    gpu_slots: int = 0
    npu_slots: int = 0
    cost_units: float = 1.0
    failure_mode: str = "ROLLBACK"  # "ROLLBACK", "COMPENSATE", "QUARANTINE_ON_DIVERGENCE", "PARTIAL_COMMIT"
    node_hash: str = ""

    def __post_init__(self) -> None:
        if not self.node_hash:
            payload = {
                "node_id": self.node_id,
                "role": self.role,
                "actor_class": self.actor_class,
                "authority_tier": self.authority_tier,
                "inputs": sorted(self.inputs),
                "outputs": sorted(self.outputs),
                "generates_provenance": self.generates_provenance,
                "evidence_level": self.evidence_level,
                "duration_ms": self.duration_ms,
                "cpu_cores": self.cpu_cores,
                "ram_units": self.ram_units,
                "gpu_slots": self.gpu_slots,
                "npu_slots": self.npu_slots,
                "cost_units": self.cost_units,
                "failure_mode": self.failure_mode,
            }
            digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
            object.__setattr__(self, "node_hash", digest)


@dataclass(frozen=True)
class RealizationGraph:
    """Executable topology G = (V, E) realizing parent intent U."""
    graph_id: str
    nodes: Mapping[str, RealizationNode]
    edges: Tuple[Tuple[str, str], ...]  # Directed edges (u, v) representing u -> v
    graph_hash: str = ""
    allow_cycle: bool = False

    def __post_init__(self) -> None:
        # 1. Edge validation
        for src, dst in self.edges:
            if src not in self.nodes:
                raise ValueError(f"Edge references non-existent source node: {src!r}")
            if dst not in self.nodes:
                raise ValueError(f"Edge references non-existent destination node: {dst!r}")

        # 2. Cycle detection (must be a valid DAG unless explicitly testing cycle rejection)
        if self._has_cycle() and not self.allow_cycle:
            raise ValueError(f"RealizationGraph {self.graph_id!r} contains a cycle; must be a valid DAG.")

        # 3. Canonical graph digest
        if not self.graph_hash:
            payload = {
                "graph_id": self.graph_id,
                "nodes": {nid: self.nodes[nid].node_hash for nid in sorted(self.nodes.keys())},
                "edges": sorted([list(e) for e in self.edges]),
            }
            digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
            object.__setattr__(self, "graph_hash", digest)

    def compute_hash(self) -> str:
        """Returns the canonical SHA-256 digest of this graph topology."""
        return self.graph_hash

    def validate_acyclic(self) -> bool:
        """Verifies whether this graph is strictly acyclic (DAG)."""
        return not self._has_cycle()

    def topological_sort(self) -> Tuple[str, ...]:
        """Returns node IDs in deterministic topological order."""
        adj: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        in_degree: Dict[str, int] = {nid: 0 for nid in self.nodes}
        for u, v in self.edges:
            adj[u].append(v)
            in_degree[v] += 1

        queue = sorted([nid for nid, deg in in_degree.items() if deg == 0])
        order: List[str] = []

        while queue:
            curr = queue.pop(0)
            order.append(curr)
            for nxt in adj[curr]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)
            queue.sort()

        if len(order) != len(self.nodes):
            raise ValueError(f"Graph {self.graph_id!r} contains a cycle.")
        return tuple(order)

    def _has_cycle(self) -> bool:
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        adj: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        for u, v in self.edges:
            adj[u].append(v)

        def dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.remove(node)
            return False

        for node in self.nodes:
            if node not in visited:
                if dfs(node):
                    return True
        return False

    def is_reachable(self, src_id: str, dst_id: str) -> bool:
        """Determines if dst_id is reachable from src_id along directed edges."""
        if src_id == dst_id:
            return True
        visited: Set[str] = set()
        queue = [src_id]
        adj: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        for u, v in self.edges:
            adj[u].append(v)

        while queue:
            curr = queue.pop(0)
            if curr == dst_id:
                return True
            for nxt in adj.get(curr, []):
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)
        return False

    def get_nodes_by_role(self, role: str) -> Tuple[RealizationNode, ...]:
        return tuple(n for n in self.nodes.values() if n.role == role)

    def roles_causally_ordered(self, pre_role: str, post_role: str, strict_immediate: bool = False) -> bool:
        """Verifies that pre_role causally precedes post_role in the topology."""
        pre_nodes = self.get_nodes_by_role(pre_role)
        post_nodes = self.get_nodes_by_role(post_role)
        if not pre_nodes or not post_nodes:
            return False

        for post in post_nodes:
            # At least one pre_node must precede this post_node
            has_pre = False
            for pre in pre_nodes:
                if strict_immediate:
                    if (pre.node_id, post.node_id) in self.edges:
                        has_pre = True
                        break
                else:
                    if self.is_reachable(pre.node_id, post.node_id):
                        has_pre = True
                        break
            if not has_pre:
                return False

            # Reverse check: post_node must NEVER reach pre_node (no inverted causality)
            for pre in pre_nodes:
                if self.is_reachable(post.node_id, pre.node_id):
                    return False

        return True

    def critical_path_duration_ms(self) -> float:
        """Calculates total critical path duration through DAG."""
        adj: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        in_degree: Dict[str, int] = {nid: 0 for nid in self.nodes}
        for u, v in self.edges:
            adj[u].append(v)
            in_degree[v] += 1

        dist: Dict[str, float] = {nid: self.nodes[nid].duration_ms for nid in self.nodes}
        queue = [nid for nid, deg in in_degree.items() if deg == 0]

        while queue:
            curr = queue.pop(0)
            for nxt in adj[curr]:
                if dist[curr] + self.nodes[nxt].duration_ms > dist[nxt]:
                    dist[nxt] = dist[curr] + self.nodes[nxt].duration_ms
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)

        return max(dist.values()) if dist else 0.0

    def total_cost_units(self) -> float:
        return sum(n.cost_units for n in self.nodes.values())

    def peak_resource_demands(self) -> Dict[str, int]:
        return {
            "max_cpu_cores": max((n.cpu_cores for n in self.nodes.values()), default=0),
            "max_ram_units": max((n.ram_units for n in self.nodes.values()), default=0),
            "max_gpu_slots": max((n.gpu_slots for n in self.nodes.values()), default=0),
            "max_npu_slots": max((n.npu_slots for n in self.nodes.values()), default=0),
        }
