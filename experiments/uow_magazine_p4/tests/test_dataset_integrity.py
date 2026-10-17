"""Unit test for P4 Frozen Corpus Split Integrity."""
import pytest
from pathlib import Path

from experiments.uow_magazine_p4.corpora.build_frozen_cases import generate_and_freeze_p4_corpus
from experiments.uow_magazine_p4.corpora.verify_split_integrity import verify_corpus_integrity


def test_frozen_dataset_generation_and_integrity(tmp_path):
    # Generate into temp dir
    manifest = generate_and_freeze_p4_corpus(output_dir=tmp_path)
    assert manifest["total_cases"] == 720
    assert manifest["splits"]["known_domain_cases"] == 360
    assert manifest["splits"]["cold_domain_cases"] == 180
    assert manifest["splits"]["adversarial_cases"] == 120
    assert manifest["splits"]["composition_cases"] == 60

    # Verify integrity
    res = verify_corpus_integrity(corpora_dir=tmp_path)
    assert res["verified"] is True
    assert res["total_cases"] == 720
