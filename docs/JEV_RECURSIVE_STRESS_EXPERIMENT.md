# JEV Recursive Multi-Axis Stress Experiment

## Purpose

Phase 1 tested recursive depth alone. Phase 2 holds the native recursive boundary fixed and varies four scale dimensions without changing the authority model:

- recursive depth;
- recursive fan-out;
- actor population;
- certified internal substitution history.

The deterministic UoW runtime remains the oracle. JEV is observer-only and never certifies legality, selects recovery, mutates state, or determines the deterministic pass/fail result.

## Preregistered profile matrix

The default matrix contains ten named profiles:

| Profile | Axis | Depth | Branching | Extra actors/runtime | Certified substitutions |
| --- | --- | ---: | ---: | ---: | ---: |
| origin | baseline | 0 | 1 | 0 | 0 |
| depth_4 | depth | 4 | 1 | 0 | 0 |
| depth_8 | depth | 8 | 1 | 0 | 0 |
| branch_2 | branching | 3 | 2 | 0 | 0 |
| branch_4 | branching | 3 | 4 | 0 | 0 |
| actors_16 | actors | 2 | 2 | 16 | 0 |
| actors_64 | actors | 2 | 2 | 64 | 0 |
| substitutions_4 | substitutions | 2 | 2 | 8 | 4 |
| substitutions_16 | substitutions | 2 | 2 | 8 | 16 |
| combined_corner | combined | 4 | 3 | 16 | 16 |

The combined corner constructs 121 governed runtimes. Every recursive edge is a real CertifiedRuntimeActor boundary.

## Conditions

Each profile is evaluated under the same three conditions:

1. baseline: no perturbation after profile construction;
2. lawful_rebind: one leaf worker is rebound to another qualified actor;
3. authority_loss: one leaf verifier becomes unavailable and the root must fail closed.

Certified substitution history is applied before all three conditions so the condition comparison does not confound substitution count.

## Deterministic gates

S0: all composition boundaries remain valid.

S1: boundary certificate hashes remain stable.

S2: every requested internal substitution is certified.

S3: successful executions contain exactly one recursive evidence link per recursive edge.

S4: successful roots expose the same declared root semantic signature.

S5: baseline and lawful-rebind states succeed while authority-loss states fail closed in every profile.

The deterministic campaign must pass all six gates before any JEV observation is interpreted.

## JEV measurement

The same frozen eight-question observer battery from Phase 1 is used. No condition label is supplied to JEV.

For each profile p:

Delta_control(p) = J_p(lawful_rebind) - J_p(baseline)

Delta_authority(p) = J_p(authority_loss) - J_p(baseline)

The preregistered observer gates are:

J0: every planned observation is complete.

J1: median authority-loss displacement is at least 2.0 times repeatability noise.

J2: median authority-loss displacement is at least 2.0 times the larger of lawful-rebind displacement or repeatability noise.

J3: minimum pairwise cosine similarity of authority-loss displacement across all profiles is at least 0.90.

J4: coefficient of variation of authority-loss displacement magnitude across profiles is at most 0.25.

Passing these gates supports only the bounded statement that this observer sees the same authority-loss transformation across the tested recursive scale surface.

## Local deterministic run

    git checkout experiment/jev-recursive-scale-invariance
    python -m qualification.jev_recursive_stress_campaign --prepare-only
    pytest tests/test_jev_recursive_stress_campaign.py -q

## Live JEV run

Install the same optional TypeSafe SDK used by Phase 1 and provide TYPESAFE_API_KEY, then run:

    python -m qualification.jev_recursive_stress_campaign

With ten profiles, three conditions, and three replicates, the default live run makes 90 provider requests.

The default artifact is:

    qualification/artifacts/jev_recursive_stress_results.json

Phase 1 remains unchanged and should be retained as the simpler depth-only reference experiment.


## Local live qualification result — 2026-09-25/26

The full live observer campaign completed against `jev-1.13.0` with all 90 planned requests valid.

Verdict:

```text
SUPPORTED_WITHIN_PREREGISTERED_STRESS_GATES
```

Measured values:

| Gate | Measured | Threshold | Result |
| --- | ---: | ---: | --- |
| J0 provider completion | 90 / 90 | 100% | PASS |
| J1 authority signal / repeatability noise | 50.64 | >= 2.0 | PASS |
| J2 authority / lawful-rebind separation | 11.89 | >= 2.0 | PASS |
| J3 minimum cross-profile cosine | 0.9845 | >= 0.90 | PASS |
| J4 authority-loss norm CV | 0.0553 | <= 0.25 | PASS |
| S0 deterministic stress oracle | 10 / 10 profiles | 100% | PASS |

Supporting measurements:

- repeatability noise floor L2: 0.0316;
- median authority-loss displacement norm: 1.6014;
- median lawful-rebind displacement norm: 0.1346;
- combined corner: 121 governed runtimes, 2,664 actors, 16 certified substitutions;
- combined-corner authority-loss cosine relative to the unnested origin: 0.9888.

Axis-specific observer invariance:

- depth 4 -> 8: minimum cosine 0.9991, norm CV 0.00198;
- fan-out 2 -> 4: minimum cosine 0.9995, norm CV 0.00442;
- actor population 16 -> 64 extra actors/runtime: minimum cosine 0.9997, norm CV 0.00351;
- substitution history 4 -> 16: minimum cosine 0.9999, norm CV 0.00356.

These results support the preregistered bounded hypothesis on this observer and stress surface. They do not establish unrestricted scale invariance outside the tested profiles or make an AGI claim.
