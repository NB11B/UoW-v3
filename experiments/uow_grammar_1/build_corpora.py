"""Generate and export corpora for Temporal and Recovery Grammars."""
import hashlib
import json
from pathlib import Path

from experiments.uow_grammar_1.grammars.temporal import generate_synthetic_corpus as gen_temporal
from experiments.uow_grammar_1.grammars.recovery import generate_synthetic_corpus as gen_recovery


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main():
    art_dir = Path("artifacts/uow_grammar_1")
    art_dir.mkdir(parents=True, exist_ok=True)

    # 1. Temporal Corpus
    t_train, t_hold = gen_temporal(seed=42)
    t_manifest = {
        "grammar": "uow.temporal.v1",
        "train_examples_count": len(t_train),
        "holdout_examples_count": len(t_hold),
        "train_examples": t_train,
        "holdout_examples": t_hold,
    }
    t_path = art_dir / "temporal_corpus_manifest.json"
    t_bytes = (json.dumps(t_manifest, indent=2) + "\n").encode("utf-8")
    t_path.write_bytes(t_bytes)
    print(f"Exported Temporal Corpus: {len(t_train)} train, {len(t_hold)} holdout -> {t_path} (SHA: {sha256_bytes(t_bytes)[:12]}...)")

    # 2. Recovery Corpus
    r_train, r_hold = gen_recovery(seed=101)
    r_manifest = {
        "grammar": "uow.recovery.v1",
        "train_examples_count": len(r_train),
        "holdout_examples_count": len(r_hold),
        "train_examples": r_train,
        "holdout_examples": r_hold,
    }
    r_path = art_dir / "recovery_corpus_manifest.json"
    r_bytes = (json.dumps(r_manifest, indent=2) + "\n").encode("utf-8")
    r_path.write_bytes(r_bytes)
    print(f"Exported Recovery Corpus: {len(r_train)} train, {len(r_hold)} holdout -> {r_path} (SHA: {sha256_bytes(r_bytes)[:12]}...)")


if __name__ == "__main__":
    main()
