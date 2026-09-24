# Final Physical Confirmation Campaign

Status: **COMPLETE — v4 physically qualified**.

The final candidate is:

`archive/uow-reduction-software-candidate-v4@9d95c11f4b09c34769e1f3a1e6d7b915291d43c8`

The consolidated F0-F8 campaign completed with live flashing enabled and satisfied both terminal closure conditions:

- `passed: true`
- `physical_claims_promotable: true`

## Final campaign result

- F0 — source attestation, build, hash, and live flash: PASS
- F1 — ESP32/UNO Q/x86 physical authority and quorum: PASS
- F2 — 1,200-job heterogeneous CPU/GPU/NPU router: PASS
- F2 — G0-G12: 13/13 PASS
- F2 — evidence continuity: 2,400/2,400 links verified
- F3 — physical NPU adaptive proposer: PASS
- F4 — physical NPU hot swap: PASS
- F5 — continuous physical adaptation: PASS
- F6 — adaptive proposer under heterogeneous physical quorum: PASS
- F7 — frozen A3 reference oracle: PASS
- F8 — candidate shadow: 279/279 PASS
- F8 — post-A3 P1-P5 policy suite: 44/44 PASS
- P1-P5 mandatory invariants: 13/13 PASS

## Hardware set

- CUDA GPU
- Intel AI Boost NPU
- host x86-64 CPU
- ESP32-S3 authority/embedded compute
- Arduino UNO Q STM32U585 authority/embedded compute
- laptop x86-64 authority participant

## Chain of custody

V4 pins the physical build and qualification inputs, including `platformio.ini`, the ESP32 interrogator, heterogeneous router campaign, physical pair/quorum clients, and NPU quorum harness. F0 rebuilt and flashed the pinned firmware and recorded binary hashes before F1-F8 executed.

Final evidence:

`qualification/artifacts/final-physical/20260924T203451Z/final-physical-campaign-summary.json`

Canonical repository summary:

`qualification/artifacts/final-physical-campaign-summary.json`

## Release conclusion

The UoW reduction, post-A3 policy integration, physical interface repair, chain-of-custody closure, and final hardware qualification are complete. Future work should branch from the v4 closeout rather than modify the sealed evidence chain.
