"""Milestone P4 Unified CLI and Qualification Orchestrator."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from experiments.uow_magazine_p4.environment_inventory import capture_environment
from experiments.uow_magazine_p4.corpora.build_frozen_cases import generate_and_freeze_p4_corpus
from experiments.uow_magazine_p4.corpora.verify_split_integrity import verify_corpus_integrity
from experiments.uow_magazine_p4.scoring.run_q1_eval import run_q1_evaluation


def main():
    parser = argparse.ArgumentParser(description="UOW-MAGAZINE-P4 Local Engineering Qualification CLI")
    subparsers = parser.add_subparsers(dest="subcommand", help="P4 qualification subcommands")

    # inventory
    subparsers.add_parser("inventory", help="Record host environment and frozen candidate identities")

    # freeze
    subparsers.add_parser("freeze", help="Generate and cryptographically freeze 720-case qualification corpus")

    # q1
    subparsers.add_parser("q1", help="Execute Gate Q1: Full semantic and authority evaluation across 720 cases")

    # q2
    q2_p = subparsers.add_parser("q2", help="Execute Gate Q2: Hardware and backend qualification")
    q2_p.add_argument("--target", choices=["laptop", "nano"], default="laptop", help="Target hardware profile")

    # q3
    subparsers.add_parser("q3", help="Execute Gate Q3: Representative physical workloads (D0/D1/D2 comparison)")

    # q4
    q4_p = subparsers.add_parser("q4", help="Execute Gate Q4: Endurance qualification")
    q4_p.add_argument("--profile", choices=["E1", "E2", "E3", "ALL"], default="ALL", help="Endurance profile to execute")

    # qualify
    subparsers.add_parser("qualify", help="Audit all gates and generate formal P4 qualification report")

    args = parser.parse_args()

    if args.subcommand == "inventory":
        capture_environment()

    elif args.subcommand == "freeze":
        generate_and_freeze_p4_corpus()
        verify_corpus_integrity()

    elif args.subcommand == "q1":
        run_q1_evaluation()

    elif args.subcommand == "q2":
        from experiments.uow_magazine_p4.backends.benchmark_pytorch import run_q2_hardware_benchmark
        run_q2_hardware_benchmark(target=args.target)

    elif args.subcommand == "q3":
        from experiments.uow_magazine_p4.workloads.workload_runner import run_q3_workloads
        run_q3_workloads()

    elif args.subcommand == "q4":
        from experiments.uow_magazine_p4.endurance.endurance_runner import run_endurance_profile
        run_endurance_profile(profile=args.profile)

    elif args.subcommand == "qualify":
        from experiments.uow_magazine_p4.audit_qualification import generate_p4_qualification_report
        generate_p4_qualification_report()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
