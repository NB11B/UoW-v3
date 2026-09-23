from __future__ import annotations

from uow_shadow.requirements import (
    Capability,
    MatchContext,
    MatcherKind,
    Requirement,
    match_requirement,
)


def test_set_inclusion_match_and_deficit():
    req = Requirement(
        requirement_id="req-cap",
        kind="actor_capability",
        matcher=MatcherKind.SET_INCLUSION,
        expected=("worker", "cpu"),
    )
    ctx = MatchContext("ctx")

    ok = match_requirement(
        req,
        Capability("cap-ok", "actor_capability", ("worker", "cpu", "storage"), "actor-A"),
        ctx,
    )
    bad = match_requirement(
        req,
        Capability("cap-bad", "actor_capability", ("worker",), "actor-B"),
        ctx,
    )

    assert ok.accepted
    assert not bad.accepted
    assert "SET_INCLUSION_FAILED" in bad.violations


def test_ordered_lattice_and_quorum_distinctness():
    ctx = MatchContext(
        "ctx",
        metadata={"order": ("PROPOSER_ONLY", "VERIFIER", "AUTHORITY_SUBSTRATE")},
    )
    authority_req = Requirement(
        "req-auth",
        "authority",
        MatcherKind.ORDERED_LATTICE,
        "VERIFIER",
    )

    assert match_requirement(
        authority_req,
        Capability("cap-auth", "authority", "AUTHORITY_SUBSTRATE", "actor-A"),
        ctx,
    ).accepted

    quorum_req = Requirement("req-q", "quorum", MatcherKind.QUORUM_K_OF_N, 2)
    duplicate_votes = Capability("cap-q", "quorum", ("A", "A"), "cluster")
    distinct_votes = Capability("cap-q2", "quorum", ("A", "B"), "cluster")

    assert not match_requirement(quorum_req, duplicate_votes, MatchContext("q")).accepted
    assert match_requirement(quorum_req, distinct_votes, MatchContext("q")).accepted


def test_freshness_requires_current_context():
    req = Requirement("req-live", "lease", MatcherKind.FRESH_CAPABILITY, True)
    cap = Capability("lease-A", "lease", True, "actor-A", freshness=10.0)

    assert match_requirement(req, cap, MatchContext("ctx", now=9.0)).accepted
    assert not match_requirement(req, cap, MatchContext("ctx", now=11.0)).accepted
