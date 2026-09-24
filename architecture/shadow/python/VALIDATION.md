# R4 Validation Record

## U1-U10
Commit 7485dbb — shadow runs 23 and 24 PASS.

## U11
Commit 63ef25a — shadow runs 25 and 26 PASS.

Preserved:
- scheduler and completion materialization as ordinary UoWs;
- independent materialization certification;
- domain execution;
- deadlock as a certified terminal transition;
- deterministic replay.

The reconstruction path does not call canonical run_orchestration.

## U12 in execution

The U12 reconstruction deliberately restores an actual threaded proposal realization rather than treating current OCC semantics alone as sufficient preservation.

Flow:

base authoritative snapshot
-> parallel worker proposal + transaction descriptor
-> deterministic core conformance
-> current-state OCC conformance
-> typed transaction-application proposal
-> explicit local authorization
-> minimal shadow AuthorizedTransition
-> shadow evidence

Important causal result under test:

whole-state precondition freshness is not the only valid freshness relation.

A transaction proposed at S_base can remain valid at S_current after disjoint commits when its recorded read/write/coupled versions still conform under OCC.

This is exactly why R2 retained typed causal coordinates rather than one universal state hash freshness rule.
