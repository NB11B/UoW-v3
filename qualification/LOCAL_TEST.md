# Local repository qualification

After the proposer seam has been merged, copy:

`uow_system_acceptance_repo.py`

to:

`qualification/uow_system_acceptance.py`

and run from the repository root.

## Fast acceptance

```powershell
python qualification/uow_system_acceptance.py
```

This uses:
- 500 randomized single-step Minsky comparisons,
- 50 terminating whole-program comparisons,
- the integrated DAG / authority / durability / external-effect / saga / replay campaign.

## Historical-strength foundation stress

To reproduce the larger Minsky qualification scale:

```powershell
python qualification/uow_system_acceptance.py `
  --step-programs 1000 `
  --steps-per-program 20 `
  --terminating-runs 500
```

That produces:
- 20,000 randomized single-step differential checks,
- 500 terminating whole-program comparisons,
- plus the integrated system acceptance campaign.

## Pass criterion

The command must exit normally with every line marked `[PASS]`.

The generated report is written by default to:

`qualification/uow_system_acceptance_report.txt`

Do not change architecture to make this campaign pass. A failure should first be treated as one of:
1. a real fidelity defect,
2. an invalid acceptance assertion,
3. an adapter mismatch caused by API naming.

The test exists to validate the architecture, not to define new architecture.
