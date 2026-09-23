# R3 Validation Record

## Shadow parity status

### Commit 195e330
Shadow workflow run 2: PASS.

Covered:
- core certification accept/reject;
- resource capacity parity;
- OCC stale-read rejection;
- external receipt binding;
- typed requirement/capability matcher basics.

### Commit 0825554
Shadow workflow run 4: PASS.

Added:
- actor capability binding parity;
- semantic projection parity;
- authority-bypass rejection;
- delegation authority attenuation.

## Canonical CI observation

The normal repository CI still fails before test execution because existing NPU test modules import optional dependencies not installed by the standard workflow:
- numpy
- openvino

The branch has not changed canonical CI dependency policy.

## R3.2 closure experiment

Next experiment:
- lower A2.7 QC-authorized graph/binding application into an ordinary UoW transition;
- compare active graph hash, active binding hash, generation, and canonical evidence;
- force wrong authorization hash and require fail-closed/no-mutation behavior.

Scope limitation:
- quorum vote formation is not claimed closed;
- quorum certificate verification is not claimed closed;
- distributed AuthoritativeHistory construction is not claimed closed.

The experiment only tests closure of the already-authorized meta-state mutation.
