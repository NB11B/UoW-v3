"""Q3B optimized inference and exact authority/evidence equivalence tests."""
from qualification.micro_operator.q3_batch import comparison, classify_batch, classify_one, commit_votes
from qualification.micro_operator.q3_cooperation import dataset, train, SEED


def test_batched_inference_is_order_preserving():
    training = dataset(6000, SEED)
    models = [train(training, (i,)) for i in range(3)]
    views = [v for _, v in dataset(121, SEED + 3)]
    assert classify_batch(models, views) == [classify_one(models, v) for v in views]


def test_batched_commit_preserves_every_certificate_and_ledger():
    observations = [0,1,1,0,0,1,0,1,1,1,0,0]
    reference, certs = commit_votes(observations, reuse_contracts=False)
    optimized, optimized_certs = commit_votes(observations, reuse_contracts=True)
    assert certs == optimized_certs
    assert reference.journal_root() == optimized.journal_root()
    for node in reference.nodes:
        assert reference.nodes[node].state.state_hash == optimized.nodes[node].state.state_hash
        assert reference.nodes[node].ledger.root_hash() == optimized.nodes[node].ledger.root_hash()


def test_q3_batch_end_to_end():
    result = comparison(count=16, repetitions=1)
    assert result["status"] == "PASS"
    assert result["same_state_evidence_certificates"]
    assert result["native_commits_per_arm"] == 16
