# UOW-NATIVE-3: Low-Rank Causal Mechanisms of Operational Grammar

Status: OPEN / ISOLATED RESEARCH. Based on UOW-NATIVE-1 sealed at `0dc8d57` and H3-Native Arm N-B historical evaluation in UoW-v2.

## Objective
Measure the causal effect of learned LoRA **weight updates** on the operational grammar of UoW proposals. Do not retrain. Do not use generic numerical comparison as the primary competence task. Keep UoW authorization independent.

### C0 — provenance and baseline reproduction
Verify local adapter file SHA-256, adapter config (rank=8, alpha=16, q_proj/v_proj, 30 layers), base model immutable revision, exact original 20-case family-disjoint corpus, decoding settings and evaluator. **Historical H3 outcomes are reference claims, not automatically reproduced**. Base and full-adapter scores must be run on identical cases with the original evaluator; any mismatch is investigated before proceeding.

### C1 — causal SVD rank ladder
For each adapted q_proj/v_proj matrix, compute actual full update `Delta W = (alpha/r) B @ A`. Construct rank-k updates for k=1,2,4 and retain original rank-8 as exact baseline. Preserve adapter scaling and shapes. Confirm `k=8` is numerically identical to original, and compare k=1,2,4 on unchanged operational evaluation. **Singular-value energy is a property of weights, not a measured fraction of behavioral change.** Do not attribute behavior to rank-1 without interventions.

### C2 — layer ablation
Using the same trained adapter, zero the adapter update at one layer at a time, and separately on prespecified blocks 0–9, 10–19, 20–29. Test Layer 28 specifically as a predefined candidate but avoid selecting only after seeing holdout. Compare outcomes using matched cases.

### C3 — unsafe outcomes and authority
Track invalid JSON, incorrect disposition, exact bindings, false unsafe YES, and model refusals separately. Run malformed or unsafe model proposals through the **actual** UoW authority and semantic policy components. A model output must never create its own certificate. Distinguish model classification errors from independently prohibited commits.

### Measurement safeguards
- Freeze training, model weights, tokenizer, generation, evaluation corpus and decoding parameters.
- Measure per-case paired changes, not only aggregate accuracy.
- Preserve original failed and corrected runs independently.
- Identify the model checkpoint and corpus by digest; do not upload weights to GitHub.
- Record 3 evaluation seeds only if sampling is enabled; deterministic greedy decoding has no meaningful sampling-seed replication.
- Stop and report `INVALID_INCOMPLETE` if the original 20-case evaluator or checkpoint cannot be accessed.
- Reuse the historical cases for reproduction; use a disjoint new holdout for confirmatory claims. No tuning on a holdout.
- Existing UoW transport/replication qualification is out of scope and unaffected.

## Start
Run `python -m unittest discover -s experiments/uow_native_3/tests -v`. See `README.md` for the local checkpoint workflow.
