# R3 Python Shadow Implementation

This directory is research-only. It is not imported by src/uow and is not part of the canonical public API.

## Purpose

The shadow package implements the R2 semantic model beside the canonical runtime.

Initial rules:

1. Shadow types carry no authority.
2. Shadow identities use SHADOW-JSON-v0.1 and are never accepted by canonical authority.
3. Accept/reject decisions in adapters are delegated to existing canonical validators.
4. No canonical validator logic is extracted during R3.0/R3.1.
5. Differences between shadow and canonical behavior are findings, not automatically normalized away.
6. Physical evidence is not upgraded by shadow parity.

## Initial package

- uow_shadow/types.py — semantic reference types.
- uow_shadow/identity.py — non-authoritative research identity profile.
- uow_shadow/requirements.py — typed requirement/capability matcher.
- uow_shadow/adapters.py — wrappers around canonical validators.

## Initial tests

The first tests exercise:
- core certification accept/reject parity;
- resource capacity parity;
- OCC stale-read rejection;
- external receipt binding;
- set-inclusion matching;
- authority lattice matching;
- distinct-voter quorum matching;
- freshness matching.

These tests are research scaffolding and do not replace canonical qualification.
