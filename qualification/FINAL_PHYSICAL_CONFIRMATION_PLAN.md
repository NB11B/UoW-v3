# Final Physical Confirmation Campaign

Status: planned terminal qualification gate.

This campaign is intentionally deferred until R7 software/repository work is complete and the final cutover candidate is frozen.

Historical physical evidence remains valid for its original qualified heads. Portable or shadow success never upgrades the final candidate to PHYSICAL.

Final sequence:

software/repository closeout -> freeze candidate -> one consolidated physical campaign -> final qualification

## Hardware set

- D1: CUDA GPU
- D2: Intel AI Boost NPU
- D3: host x86-64 CPU
- D4: ESP32-S3 authority/embedded compute
- D5: Arduino UNO Q STM32U585 authority/embedded compute
- Authority quorum where required: ESP32-S3 + STM32U585 + Laptop x86-64, 2-of-3

## F0 Candidate attestation

Record candidate commit, package/version, firmware source SHA and binary hashes, actual device identities, CPU/GPU/NPU backend identities, transports, authority profile version, wire/protocol version, and claim-registry digest.

Fallback/substitution must never retain the requested physical label.

## F1 Embedded authority

Reconfirm ESP32 authority rejection, evidence-chain recomputation, ESP32/STM32 pair agreement, stale catch-up, divergence quarantine, 2-of-3 ESP32/STM32/x86 quorum, insufficient quorum rejection, conflicting-transition rejection, duplicate authorization idempotency, and physical L4/L5 authority-hash parity.

Claims: ESP32.AUTHORITY; EVIDENCE.CHAIN; DIST.AUTHORITY.PAIR_AGREEMENT.PHYSICAL; DIST.AUTHORITY.QUORUM_2_OF_3.PHYSICAL.

## F2 Heterogeneous execution

Reconfirm actual CPU, CUDA GPU, and OpenVINO NPU execution; no silent substitution; measured performance from the named substrate; authority fixed outside adaptive proposal.

Claims: HETERO.EXECUTION; HETERO.ADAPTATION; HETERO.PERFORMANCE.

## F3 Physical adaptive proposer

Reconfirm physical NPU inference, zero proposer authority, rejection of illegal proposals, certified feedback, and no CPU fallback labeled NPU.

Claim: U15.NPU_ADAPTIVE_PROPOSER.PHYSICAL.

## F4 Physical hot swap

Reconfirm staging generation, NPU health check, atomic promotion, continuous work progress, corrupt staging rejection, rollback/restart recovery, and zero wrong commits.

Claim: U15.NPU_HOT_SWAP.PHYSICAL.

## F5 Continuous physical adaptation

Reconfirm repeated live generations under workload drift, reversal, observation corruption, continued NPU execution, no reset, and zero wrong commits.

Claim: U15.CONTINUOUS_ADAPTATION_ENDURANCE.PHYSICAL.

## F6 Adaptive proposer under heterogeneous physical quorum

Reconfirm NPU proposer -> 2-of-3 heterogeneous authority -> authoritative transition -> certified feedback -> adaptation.

Exercise all required voter combinations, authority loss, minority partition, hot swap under quorum, quorum-certified feedback, and zero wrong commits.

Claim: U15.ADAPTIVE_QUORUM_ORCHESTRATION.PHYSICAL.

## F7 A3 physical continuum confirmation

At minimum rerun affected physical A3 gates for GPU/NPU/CPU characterization, repeated crossover, ESP32/STM32 characterization, minimum-adequate placement, deterministic/dynamic substitution, power-envelope behavior, heterogeneous graph execution including transfer cost, and semantic-equivalence/correctness gates.

If final code materially changes the power model, transfer model, device-selection policy, measurement source, physical executor, or A3 policy lifecycle, rerun the relevant full A3 characterization/endurance campaign.

The historical 12,000-UoW A3.8 soak remains evidence for its original qualified head. A new 12,000-UoW soak is required only if the final release claims that same endurance scope for a changed mechanism.

## F8 Policy P1-P5 final-candidate confirmation

Run the frozen P1-P5 acceptance suite against the final facade/cutover candidate while physical providers are available.

Confirm all 13 invariants: U-to-W projection, deterministic snapshot resolution, graph realization, qualified policy registry, discovery without authority, prospective promotion, deterministic policy reuse, safe drift invalidation, transactional registry versioning, distributed policy authority, durable recovery, zero duplicate external effects, and five-tier provenance.

No P6 is required.

## Result semantics

Each physical claim records observed_pass, qualified, passed = observed_pass AND qualified, actual components, substitutions/fallbacks, candidate commit, firmware hashes, and artifact paths.

## Final acceptance

The final candidate can be promoted as physically qualified only when every physical claim required for the intended release scope passes. A failure blocks only the affected physical claim/release scope until corrected and rerun.