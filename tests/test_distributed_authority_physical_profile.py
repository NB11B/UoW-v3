from qualification.distributed_authority.physical_profile import (
    PhysicalAuthorityNode,
    assess_topology,
    current_local_profile,
)


def test_current_profile_recognizes_uno_q_as_one_physical_failure_domain():
    nodes = current_local_profile()
    assert len(nodes) == 2
    uno = next(node for node in nodes if node.board_model == "Arduino UNO Q")
    assert "STM32U585" in uno.authority_domain
    assert any("QRB2210" in domain for domain in uno.service_domains)

    assessment = assess_topology(nodes)
    assert assessment.independent_failure_domains == 2
    assert assessment.pair_qualification_ready is True
    assert assessment.two_of_three_quorum_ready is False


def test_multiple_processors_on_same_board_do_not_inflate_quorum_count():
    nodes = list(current_local_profile())
    nodes.append(
        PhysicalAuthorityNode(
            node_id="B-linux",
            board_model="Arduino UNO Q",
            transport="internal Bridge/RPC",
            endpoint="internal",
            authority_domain="QRB2210 Linux process",
            service_domains=(),
            failure_domain="arduino-uno-q-com5",
        )
    )

    assessment = assess_topology(nodes)
    assert assessment.physical_nodes == 3
    assert assessment.authority_domains == 3
    assert assessment.independent_failure_domains == 2
    assert assessment.two_of_three_quorum_ready is False


def test_third_independent_board_enables_physical_two_of_three_profile():
    nodes = list(current_local_profile())
    nodes.append(
        PhysicalAuthorityNode(
            node_id="C",
            board_model="future-independent-board",
            transport="independent",
            endpoint="future",
            authority_domain="deterministic authority",
            service_domains=(),
            failure_domain="third-independent-board",
        )
    )
    assessment = assess_topology(nodes)
    assert assessment.independent_failure_domains == 3
    assert assessment.two_of_three_quorum_ready is True


def test_tri_heterogeneous_profile_has_three_independent_failure_domains():
    from qualification.distributed_authority.physical_profile import tri_heterogeneous_profile
    nodes = tri_heterogeneous_profile()
    assert len(nodes) == 3
    assessment = assess_topology(nodes)
    assert assessment.independent_failure_domains == 3
    assert assessment.pair_qualification_ready is True
    assert assessment.two_of_three_quorum_ready is True
    assert "2-of-3 physical quorum can be qualified" in assessment.reasons

