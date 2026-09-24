# R4 Validation Record

## U1-U10
Shadow runs 23 and 24: PASS.

## U11
Shadow runs 25 and 26: PASS.

## U12
Shadow runs 27 and 28: PASS.

## U13
Commit d44209b — shadow runs 29 and 30: PASS.

Preserved:
- requirement binding;
- leased-resource lifecycle;
- consumable budget debit;
- atomic resource-aware scheduler materialization;
- over-allocation failure;
- forged requirement failure;
- legal policy diversity;
- deterministic replay.

## U14 next

Proposer reconstruction deliberately excludes ProposerOrchestrationEngine and run_proposer_orchestration.

Flow:

non-authoritative proposer
-> deterministic canonical proposal judge
-> deterministic fallback if required
-> certified resource scheduler materialization
-> minimal shadow authority transition
-> telemetry

The proposer is never passed an authority object or mutation interface.

Portable proposer-swappability is reconstructed separately from physical NPU evidence; physical U15/HETERO claims remain later reconstruction obligations.
