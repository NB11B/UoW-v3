# R4 Experiment Reconstruction Exit Record

Control baseline: `main@f4dc767322233cd3bd9afc6c1b7af45a3987111d`

## Portable reconstruction result

The research shadow suite now reconstructs the complete portable experiment chain using the R2/R3 semantic architecture.

| Experiment | Result | Shadow runs |
|---|---|---|
| U1-U10 | RECONSTRUCTED_INITIAL | 23/24 |
| U11 | RECONSTRUCTED_INITIAL | 25/26 |
| U12 | RECONSTRUCTED_INITIAL | 27/28 |
| U13 | RECONSTRUCTED_INITIAL | 29/30 |
| U14 | RECONSTRUCTED_INITIAL | 31/32 |
| U14-B | RECONSTRUCTED_INITIAL; archive gap closed | 33/34 |
| Q1 | RECONSTRUCTED_INITIAL | 37/38 |
| U15.1-U15.4 portable | RECONSTRUCTED_INITIAL | 39/41/42 |
| distributed authority portable | RECONSTRUCTED_INITIAL | 53/54 |
| A2.0-A2.5 | RECONSTRUCTED_INITIAL | 53/54 |
| A2.6 | RETAINED_REALIZATION + reconstructed compatibility | 55/56 |
| A2.7 | RECONSTRUCTED_INITIAL | 55/56 |
| A2.8 | RECONSTRUCTED_INITIAL | 57/58 |

Latest A2.8 suite: **115 passed**.

## A2.8 numerical parity

The reconstructed A2.8 runtime is required to reproduce the original 40-step seed-42 comparison to two decimals:

- B0 fixed: 8299.78
- B1 rule-based: 5934.51
- A2 reconstructed adaptive: 5907.99

The capstone also preserves:
- semantic projection at every tested step;
- zero wrong commit;
- zero uncertified mutation;
- zero stale accepted mutation;
- zero lost task;
- topology lineage;
- quorum signers;
- anti-thrashing hysteresis;
- poisoned-observation containment;
- duplicate task protection;
- WAL replay.

## What R4 did not erase

The following remain separate retained realizations/evidence:
- physical Intel NPU execution;
- physical ESP32/STM32/x86 authority;
- physical hot-swap and endurance evidence;
- OpenVINO/CUDA-specific adapters;
- wire transport;
- WAL/fsync durability;
- external physical effects.

Portable reconstruction does not upgrade, replace, or invalidate physical evidence.

## Architectural conclusions supported by R4

1. The native transition authority core can be represented as:
   Proposal -> Conformance -> Authorization -> AuthorizedTransition -> Evidence.

2. Higher-order runtime application is substantially closed under that grammar:
   graph substitution, rebinding, delegation registration, history adoption, and QC-authorized mutation.

3. Authorization formation is not forced into state-transition closure:
   quorum vote/QC formation remains an attestation protocol.

4. External physical invocation remains a true external-effect boundary.

5. Whole-state hash freshness is not universal:
   U12 requires typed OCC causal compatibility.

6. Cursor ownership is not universal:
   Q1 demonstrates detached certified control-plane transitions.

7. A2.6 transport and durability mechanisms are realizations, not axioms.

## R4 disposition

`R4_PORTABLE_RECONSTRUCTION = COMPLETE_INITIAL`.

Physical replay remains a retained local-hardware obligation. No production code is eligible for removal merely because its portable semantics have reconstructed.
