"""Reference encoder for Heterogeneous Authority Hash Profile v1."""
from __future__ import annotations

import hashlib
import json
from typing import Optional, Sequence


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_state(r0: int, r1: int, pc: int, sequence: int, halted: bool) -> str:
    return f"r0={r0};r1={r1};pc={pc};sequence={sequence};halted={1 if halted else 0}"


def canonical_proposal(
    pre_state_hash: str,
    post_state_hash: str,
    pc: int,
    halted: bool,
) -> str:
    return f"pre={pre_state_hash};post={post_state_hash};pc={pc};halted={1 if halted else 0}"


def canonical_certificate(proposal_hash: str, valid: bool, reason_code: int) -> str:
    return f"proposal={proposal_hash};valid={1 if valid else 0};reason={reason_code}"


def canonical_evidence(
    step: int,
    pre_state_hash: str,
    post_state_hash: str,
    proposal_hash: str,
    certificate_hash: str,
    prev_root: str,
) -> str:
    return (
        f"step={step};pre={pre_state_hash};post={post_state_hash};"
        f"proposal={proposal_hash};certificate={certificate_hash};prev={prev_root}"
    )


def canonical_vote(
    *,
    accepted: bool,
    certificate_hash: str,
    evidence_step: int,
    node_id: str,
    pre_evidence_root: str,
    pre_state_hash: str,
    proposal_hash: str,
    proposed_state_hash: str,
    rejection_reason: Optional[str],
    ruleset_version: str,
) -> str:
    payload = {
        "accepted": accepted,
        "certificate_hash": certificate_hash,
        "evidence_step": evidence_step,
        "node_id": node_id,
        "pre_evidence_root": pre_evidence_root,
        "pre_state_hash": pre_state_hash,
        "proposal_hash": proposal_hash,
        "proposed_state_hash": proposed_state_hash,
        "rejection_reason": rejection_reason if rejection_reason else None,
        "ruleset_version": ruleset_version,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_qc(
    *,
    certificate_hash: str,
    committed_state_hash: str,
    evidence_step: int,
    expected_evidence_root: str,
    pre_evidence_root: str,
    pre_state_hash: str,
    proposal_hash: str,
    proposed_state_hash: str,
    ruleset_version: str,
    threshold: int,
    uow_id: str,
    vote_hashes: Sequence[str],
    voters: Sequence[str],
) -> str:
    payload = {
        "certificate_hash": certificate_hash,
        "committed_state_hash": committed_state_hash,
        "evidence_step": evidence_step,
        "expected_evidence_root": expected_evidence_root,
        "pre_evidence_root": pre_evidence_root,
        "pre_state_hash": pre_state_hash,
        "proposal_hash": proposal_hash,
        "proposed_state_hash": proposed_state_hash,
        "ruleset_version": ruleset_version,
        "threshold": threshold,
        "uow_id": uow_id,
        "vote_hashes": list(vote_hashes),
        "voters": list(voters),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
