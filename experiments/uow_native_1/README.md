# UOW-NATIVE-1: bounded native-circuit pilot

Status: **synthetic feasibility pilot only**. This is not evidence of Goodfire's claims about real LLM neurons, not UoW conformance qualification, and not production integration.

Motivation: [Neural Networks Are Already Clean](https://already-clean.goodfire.com/). Test whether an existing, frozen learned network contains an intervention-sensitive relational signal, and whether output proposals can be denied by an independent deterministic gate.

## Reproduce

Requires Python 3.10+ and PyTorch. From this directory:

```bash
python -m unittest -v test_experiment.py
python experiment.py --seeds 3 --output report.json
```

The training task is `a > b`, with independent held-out examples and a shifted coordinate range; the tiny two-layer MLP has 12 tanh hidden units. For each seed, we first train then freeze all weights. Select a candidate unit using **training data only**; ablate it and compare against 11 other single-unit ablations on held-out test inputs. Separately verify that unauthorized and stale proposals never commit through a toy fail-closed gate.

## Evidence and limits

This is a synthetic learned classifier, not a pretrained LLM. There are no matched-weight random-neuron null distributions, no SAE baseline, no semantic paraphrase holdouts, and no end-to-end UoW transport integration. The toy authorization predicate only checks an elementary invariant; production UoW conformance is neither exercised nor implied. Test-derived neuron effects are small and may vary with seed. This does **not** demonstrate an independently executable neuron capability or efficiency gains.

Follow-on experiment should use a frozen small pretrained model, causal interventions with preregistered thresholds, contextual controls, and the existing UoW proposal API. Keep on a research branch until separately qualified.
