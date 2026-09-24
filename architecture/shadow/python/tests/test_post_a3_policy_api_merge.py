from __future__ import annotations

import uow
import uow.policy as policy_api


def test_post_a3_policy_namespace_is_part_of_canonical_api():
    assert uow.policy is policy_api
    assert policy_api.PolicyRegistry is not None
    assert policy_api.PolicyResolver is not None
    assert policy_api.DistributedPolicyGovernor is not None
    assert policy_api.DurablePolicyStore is not None
    assert policy_api.NodeRecoveryCoordinator is not None


def test_policy_graph_semantics_remain_namespaced_not_flattened():
    assert uow.RealizationGraph is not policy_api.RealizationGraph
    assert "policy" in uow.__all__
    assert "RealizationGraph" in policy_api.__all__


def test_post_a3_policy_api_carries_p1_p5_terminal_surfaces():
    required = {
        "WorkRequirement",
        "WorldConditions",
        "PolicyRegistry",
        "PolicyResolver",
        "DiscoveryEngine",
        "QualificationEngine",
        "MultidimensionalDriftMonitor",
        "DistributedPolicyGovernor",
        "DurablePolicyStore",
        "NodeRecoveryCoordinator",
        "RecoveryRecord",
        "ExecutionCertificate",
    }
    assert required.issubset(set(policy_api.__all__))
