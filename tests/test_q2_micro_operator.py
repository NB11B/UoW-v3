"""Q2 regression against the existing UoW production certifier and D1 quorum."""
from qualification.micro_operator.q2_campaign import run_q2, train_model, split, target


def test_q2_all_gates():
    report = run_q2()
    assert report["passed"], report
    assert len(report["gates"]) == 9
    assert report["physical_transport_qualified"] is False


def test_q2_training_reproducible_and_heldout():
    first = train_model()
    assert first == train_model()
    _, heldout = split()
    accuracy = sum(first.predict(*xy) == target(*xy) for xy in heldout) / len(heldout)
    assert accuracy >= .95
