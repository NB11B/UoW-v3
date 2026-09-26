# JEV Recursive-Scale UoW Experiment

## Purpose

This is one bounded qualification experiment, not a family of nested campaigns.
It asks one question:

> Does the semantic displacement associated with the same bounded authority-loss perturbation remain stable as an otherwise equivalent governed UoW is embedded at greater recursive depth?

The experiment is built on the current recursive composition boundary. A governed child runtime may appear as one parent actor only after its own realization is certified. Child-local roles are not flattened into the parent graph. The parent sees the certified boundary, and child execution evidence is linked upward.

## Separation of responsibilities

The UoW runtime is the deterministic source of truth. It decides whether a graph conforms, whether a boundary certificate verifies, whether an actor is available, whether execution succeeds, and whether a commit path is legal.

JEV is an observer only. It does **not** calculate thresholds, certify a graph, decide legality, mutate state, select a recovery action, or determine the final experiment verdict. This follows the existing JEV engineering rule that deterministic facts stay in code and JEV receives only bounded interpretive questions.

The TypeSafe SDK is isolated in `qualification/jev_provider.py`; the experiment module never imports the vendor SDK.

## Why this uses an eight-coordinate JEV observer instead of the older 29-D discourse instrument

The Green Valley v0.5.1 JEV instrument was designed around discourse state (`passage`, `target_proposition`, `target_subject`) and produced a 29-D probability representation with an eight-dimensional canonical projection. Reusing those discourse-specific probes for a UoW control system would mix two different semantic domains.

This test therefore reuses the **measurement method**, not the discourse probe vocabulary: a fixed probability-state vector is measured before and after a controlled transition and the displacement is compared across scale. The UoW-specific observer is a frozen eight-Noul battery, so every API response is directly a vector in `R^8`.

## Experimental surface

Default recursion depths are 0, 1, 2, and 3. At each depth the harness creates fresh runtimes and evaluates exactly three conditions:

1. `baseline` — all actors are available and the root executes successfully.
2. `lawful_rebind` — the leaf worker is rebound to another qualified actor without changing the contract or composition certificate; the root must still execute successfully.
3. `authority_loss` — the leaf verifier becomes unavailable; the recursive execution must fail closed with `ACTOR_UNAVAILABLE` and must not bypass certification.

The state given to JEV contains only normalized observed facts. It does not contain the condition label. The same fixed question battery is used for every state.

With the defaults there are:

- 4 recursion depths;
- 3 states per depth;
- 3 repeated JEV measurements per state;
- 8 questions batched in each `system_one` request;
- **36 live API requests total**.

## Primary measurement

Let `J_d(c)` be the mean eight-dimensional JEV probability vector at recursive depth `d` and condition `c`.

The control displacement is

```text
Delta_rebind(d) = J_d(lawful_rebind) - J_d(baseline)
```

and the tested operator displacement is

```text
Delta_authority(d) = J_d(authority_loss) - J_d(baseline).
```

The experiment tests whether `Delta_authority(d)` is recognizably the same operator as depth increases.

## Engineering gates

The default thresholds are preregistered engineering gates for this experiment, not universal constants:

- **U0 Deterministic oracle:** baseline and lawful rebind succeed; authority loss fails closed; all composition boundaries remain valid; certificates do not drift.
- **J0 Provider completeness:** every planned observation returns one valid eight-coordinate vector.
- **J1 Detectability:** median authority-loss displacement is at least `2.0x` the measured within-state repeatability floor.
- **J2 Control separation:** median authority-loss displacement is at least `2.0x` the larger of the lawful-rebind displacement or repeatability floor.
- **J3 Direction invariance:** minimum pairwise cosine similarity of authority-loss displacement across depths is at least `0.90`.
- **J4 Magnitude invariance:** coefficient of variation of authority-loss displacement magnitude across depths is at most `0.25`.

The output is `SUPPORTED_WITHIN_PREREGISTERED_ENGINEERING_GATES` only when all six gates pass. This is evidence about this bounded operator and observer surface; it is not, by itself, an AGI claim.

## Local run

Fetch the branch and install the repository exactly as documented by UoW, then add the optional live JEV SDK:

```powershell
git fetch origin
git checkout experiment/jev-recursive-scale-invariance
python -m pip install -e .
python -m pip install pytest
python -m pip install "typesafe-sdk>=0.7.1,<0.8"
$env:TYPESAFE_API_KEY="<your key>"
```

First validate the deterministic UoW surface with no API calls:

```powershell
python -m qualification.jev_recursive_scale_campaign --prepare-only
pytest tests/test_jev_recursive_scale_campaign.py -q
```

Then run the live experiment:

```powershell
python -m qualification.jev_recursive_scale_campaign
```

The default artifact is:

```text
qualification/artifacts/jev_recursive_scale_results.json
```

The live runner pins `jev-1.13.0` by default and rejects an unexpected resolved model. To deliberately test a moving alias or another model, pass `--model <model-id>` and treat it as a separate run.

## Interpretation

There are three useful outcomes.

If direction and magnitude are stable across depth, the test supports the narrow proposition that JEV observes authority loss as a scale-stable semantic/control transformation on this recursive UoW surface.

If the signal is detectable but changes with depth, then recursive embedding changes the observer geometry and the scale-invariance hypothesis is not supported.

If authority loss is not distinguishable from lawful rebinding or from repeatability noise, then this JEV observer surface is not resolving the operational distinction well enough to support the hypothesis.
