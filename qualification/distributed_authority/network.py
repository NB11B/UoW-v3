"""Deterministic network-fault model and bounded self-healing controller.

The fabric is a PORTABLE qualification model, not evidence of a physical
network. It models reachability and alternate routing. The healing controller
may automatically catch up a node only when its current state/evidence pair is a
verified prefix of quorum-certified history.

Divergent history is quarantined. Rebuild is explicit.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Iterable, Optional

if TYPE_CHECKING:
    from .authority import AuthorityNode, DistributedAuthorityCluster


class NetworkFabric:
    """Small undirected faultable graph with deterministic shortest-path routing."""

    def __init__(self, nodes: Iterable[str] = ()) -> None:
        self.nodes: set[str] = set(nodes)
        self._links: dict[tuple[str, str], bool] = {}

    @staticmethod
    def _edge(a: str, b: str) -> tuple[str, str]:
        if a == b:
            raise ValueError("Self-links are not network edges.")
        return tuple(sorted((a, b)))

    def add_node(self, node_id: str) -> None:
        self.nodes.add(node_id)

    def connect(self, a: str, b: str, *, up: bool = True) -> None:
        self.nodes.update((a, b))
        self._links[self._edge(a, b)] = bool(up)

    def set_link(self, a: str, b: str, up: bool) -> None:
        edge = self._edge(a, b)
        if edge not in self._links:
            raise KeyError(f"Unknown link {edge}.")
        self._links[edge] = bool(up)

    def link_up(self, a: str, b: str) -> bool:
        return self._links.get(self._edge(a, b), False)

    def neighbors(self, node_id: str) -> tuple[str, ...]:
        out: list[str] = []
        for (a, b), up in self._links.items():
            if not up:
                continue
            if a == node_id:
                out.append(b)
            elif b == node_id:
                out.append(a)
        return tuple(sorted(out))

    def route(self, source: str, destination: str) -> Optional[tuple[str, ...]]:
        if source not in self.nodes or destination not in self.nodes:
            return None
        if source == destination:
            return (source,)

        queue: deque[tuple[str, tuple[str, ...]]] = deque([(source, (source,))])
        visited = {source}
        while queue:
            current, path = queue.popleft()
            for neighbor in self.neighbors(current):
                if neighbor in visited:
                    continue
                next_path = path + (neighbor,)
                if neighbor == destination:
                    return next_path
                visited.add(neighbor)
                queue.append((neighbor, next_path))
        return None

    def isolate_node(self, node_id: str) -> None:
        for edge in list(self._links):
            if node_id in edge:
                self._links[edge] = False

    def restore_link(self, a: str, b: str) -> None:
        self.set_link(a, b, True)

    def topology(self) -> dict[str, object]:
        return {
            "nodes": sorted(self.nodes),
            "links": [
                {"a": a, "b": b, "up": up}
                for (a, b), up in sorted(self._links.items())
            ],
        }


class HealingAction(str, Enum):
    ALREADY_CONVERGED = "ALREADY_CONVERGED"
    REROUTED = "REROUTED"
    CAUGHT_UP = "CAUGHT_UP"
    NETWORK_ISOLATED = "NETWORK_ISOLATED"
    QUARANTINED_DIVERGENCE = "QUARANTINED_DIVERGENCE"
    QUARANTINED_REPLAY_FAILURE = "QUARANTINED_REPLAY_FAILURE"
    REBUILT = "REBUILT"


@dataclass(frozen=True)
class HealingResult:
    node_id: str
    action: HealingAction
    success: bool
    before_state_hash: str
    after_state_hash: str
    before_evidence_root: str
    after_evidence_root: str
    entries_replayed: int = 0
    route: tuple[str, ...] = ()
    detail: str = ""


class SelfHealingController:
    """Bounded recovery around a DistributedAuthorityCluster.

    Automatic operations:
    - alternate-path routing;
    - stale-prefix catch-up from quorum-certified journal entries.

    Explicitly non-automatic:
    - replacement of divergent/corrupt history.
      Such nodes are quarantined and require explicit_rebuild(authorize=True).
    """

    def __init__(self, cluster: "DistributedAuthorityCluster") -> None:
        self.cluster = cluster
        self.events: list[HealingResult] = []

    def reroute(self, destination: str, *, source: Optional[str] = None) -> HealingResult:
        src = source or self.cluster.ingress
        node = self.cluster.nodes[destination]
        before_state = node.state.state_hash
        before_root = node.ledger.root_hash()
        route = self.cluster.network.route(src, destination)
        if route is None:
            result = HealingResult(
                destination,
                HealingAction.NETWORK_ISOLATED,
                False,
                before_state,
                before_state,
                before_root,
                before_root,
                detail=f"no route from {src}",
            )
        else:
            direct = len(route) <= 2
            result = HealingResult(
                destination,
                HealingAction.ALREADY_CONVERGED if direct else HealingAction.REROUTED,
                True,
                before_state,
                before_state,
                before_root,
                before_root,
                route=route,
                detail="direct route" if direct else "alternate path selected",
            )
        self.events.append(result)
        return result

    def heal_node(self, node_id: str) -> HealingResult:
        node = self.cluster.nodes[node_id]
        before_state = node.state.state_hash
        before_root = node.ledger.root_hash()
        route = self.cluster.network.route(self.cluster.ingress, node_id)
        if route is None:
            result = HealingResult(
                node_id,
                HealingAction.NETWORK_ISOLATED,
                False,
                before_state,
                before_state,
                before_root,
                before_root,
                route=(),
                detail="replica is unreachable; no mutation attempted",
            )
            self.events.append(result)
            return result

        prefix = self.cluster.prefix_index_for(node)
        if prefix is None:
            node.quarantine()
            result = HealingResult(
                node_id,
                HealingAction.QUARANTINED_DIVERGENCE,
                False,
                before_state,
                node.state.state_hash,
                before_root,
                node.ledger.root_hash(),
                route=route,
                detail="state/evidence pair is not a verified quorum-journal prefix",
            )
            self.events.append(result)
            return result

        if prefix == len(self.cluster.journal):
            node.activate()
            result = HealingResult(
                node_id,
                HealingAction.ALREADY_CONVERGED,
                True,
                before_state,
                node.state.state_hash,
                before_root,
                node.ledger.root_hash(),
                route=route,
            )
            self.events.append(result)
            return result

        replayed = 0
        for entry in self.cluster.journal[prefix:]:
            apply = node.apply_quorum_certificate(
                entry.uow,
                entry.proposal,
                entry.quorum_certificate,
            )
            if not (apply.applied or apply.idempotent):
                node.quarantine()
                result = HealingResult(
                    node_id,
                    HealingAction.QUARANTINED_REPLAY_FAILURE,
                    False,
                    before_state,
                    node.state.state_hash,
                    before_root,
                    node.ledger.root_hash(),
                    entries_replayed=replayed,
                    route=route,
                    detail=apply.reason,
                )
                self.events.append(result)
                return result
            replayed += 1

        expected_state, expected_root, expected_steps = self.cluster.expected_tip()
        success = (
            node.state.state_hash == expected_state
            and node.ledger.root_hash() == expected_root
            and len(node.ledger.records) == expected_steps
        )
        if not success:
            node.quarantine()
            action = HealingAction.QUARANTINED_REPLAY_FAILURE
        else:
            node.activate()
            action = HealingAction.CAUGHT_UP

        result = HealingResult(
            node_id,
            action,
            success,
            before_state,
            node.state.state_hash,
            before_root,
            node.ledger.root_hash(),
            entries_replayed=replayed,
            route=route,
        )
        self.events.append(result)
        return result

    def explicit_rebuild(self, node_id: str, *, authorize: bool = False) -> HealingResult:
        if not authorize:
            raise PermissionError(
                "Divergent authority history cannot be silently overwritten; explicit authorization is required."
            )

        # Import here to avoid a runtime circular dependency.
        from .authority import AuthorityNode, NodeMode

        old = self.cluster.nodes[node_id]
        before_state = old.state.state_hash
        before_root = old.ledger.root_hash()
        replacement = AuthorityNode(
            node_id,
            old.initial_state,
            ruleset_version=old.ruleset_version,
            clock_start=old.clock_ticks,
            clock_stride=old.clock_stride,
            clock_frozen=old.clock_frozen,
        )
        self.cluster.replace_node(node_id, replacement)

        replayed = 0
        for entry in self.cluster.journal:
            apply = replacement.apply_quorum_certificate(
                entry.uow,
                entry.proposal,
                entry.quorum_certificate,
            )
            if not (apply.applied or apply.idempotent):
                replacement.quarantine()
                result = HealingResult(
                    node_id,
                    HealingAction.QUARANTINED_REPLAY_FAILURE,
                    False,
                    before_state,
                    replacement.state.state_hash,
                    before_root,
                    replacement.ledger.root_hash(),
                    entries_replayed=replayed,
                    detail=apply.reason,
                )
                self.events.append(result)
                return result
            replayed += 1

        expected_state, expected_root, expected_steps = self.cluster.expected_tip()
        success = (
            replacement.state.state_hash == expected_state
            and replacement.ledger.root_hash() == expected_root
            and len(replacement.ledger.records) == expected_steps
        )
        replacement.mode = NodeMode.ACTIVE if success else NodeMode.QUARANTINED
        result = HealingResult(
            node_id,
            HealingAction.REBUILT if success else HealingAction.QUARANTINED_REPLAY_FAILURE,
            success,
            before_state,
            replacement.state.state_hash,
            before_root,
            replacement.ledger.root_hash(),
            entries_replayed=replayed,
            route=self.cluster.network.route(self.cluster.ingress, node_id) or (),
            detail="explicit verified rebuild from genesis + quorum journal",
        )
        self.events.append(result)
        return result
