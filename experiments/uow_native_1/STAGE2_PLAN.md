# UOW-NATIVE-1 Stage 2: pretrained model intervention protocol

Status: **runner implemented locally; pretrained model NOT EXECUTED**.

## Preregistered objective
Evaluate whether a native MLP hidden channel in an unmodified frozen pretrained causal LM has a reproducible causal effect on a relational comparison task, stronger than random-neuron controls. This does not equate a neuron with an independent UoW operator.

## Exact design
- Model: HuggingFaceTB/SmolLM2-135M-Instruct; pin immutable Hugging Face commit SHA before running.
- Each seed trains **nothing**; model parameters frozen.
- Score single-token greater-number candidates by next-token logit margin. Reject examples whose candidates do not each tokenize to exactly one token.
- Use 24 train-only selection prompts, 48 held-out paraphrases, and 48 shifted-template prompts. Generate disjoint pairs with fixed seeds; balanced ordering.
- Randomly sample 32 intermediate MLP neurons at the last `mlp.down_proj`. On selection set, select the neuron with greatest absolute ablation margin difference. Freeze choice.
- On held-out set, compare selected-neuron zero-ablation against baseline and the other 31 randomly sampled neurons.
- Null rank p = (1 + number of controls with effect >= selected effect)/(1 + number of controls); report exact effect and rank p.
- Report held-out and shifted accuracy and logit margin, not just selection improvement. Repeat with three independent seeds before drawing conclusions.
- Every intervention is a scoped forward-pre-hook removed even if inference fails.

## Acceptance and stopping
A promising result requires p < 0.05 for the predeclared contrast for **all three** independently seeded runs and nontrivial, consistent held-out effect. Also require a confirmed baseline task score above chance and correct end-to-end UoW PROPOSE -> CERTIFY -> COMMIT authority rejection on stale/falsified proposals. Multiple seeds and module choices require correction if used for inferential claims. A nonpassing run is retained as negative evidence. No further exploratory tuning after reviewing held-out results.

## Execution
Complete Python runner and its CPU-only tests are supplied separately as `pretrained_probe.py` and `test_pretrained_probe.py`. After installing the declared optional dependencies, run:

```bash
python -m unittest -v test_pretrained_probe.py
python pretrained_probe.py --model HuggingFaceTB/SmolLM2-135M-Instruct --revision <IMMUTABLE_HF_COMMIT_SHA> --seed 42 --output pretrained_report.json
```

Do not claim Goodfire replication, independent neuron execution, end-to-end authority conformance, or energy savings from this experiment. Pilot evidence does not qualify Stage 2.
