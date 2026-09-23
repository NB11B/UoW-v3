# R3 Validation Record

## Commit 195e330

Shadow test workflow:
- workflow: UoW Closure Shadow
- run: 2
- result: PASS

Initial shadow tests executed successfully against the canonical package.

Covered:
- core certification accept/reject;
- resource capacity parity;
- OCC stale-read rejection;
- external receipt binding;
- typed requirement/capability matcher basics.

## Canonical CI observation

The ordinary CI run on the same research PR did not reach canonical test execution because collection failed on missing optional dependencies:
- numpy
- openvino

The standard workflow installs only the editable UoW package and pytest.

This failure is not attributed to shadow code; it occurs during import of existing NPU test modules.

No change to canonical CI dependency policy is made in R3.

## Next validation expansion

R3.1 adds parity tests for:
- actor capability binding;
- semantic projection with authority-bypass negative control;
- delegation authority attenuation.

Qualification status remains research-only. Shadow parity does not upgrade evidence level.
