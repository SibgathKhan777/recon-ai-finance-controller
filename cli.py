"""Single entry point: generate synthetic data, run the pipeline, print a summary.

    python cli.py demo                     # generate + run, zero setup
    python cli.py generate --corrupt currency
    python cli.py run
"""
import argparse

from recon.generate_data import generate
from recon.pipeline import run as run_pipeline


def main():
    parser = argparse.ArgumentParser(description="AI Finance Controller - reconciliation agent")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="generate data and run the full pipeline")
    demo.add_argument("--seed", type=int, default=42)
    demo.add_argument("--corrupt", choices=["none", "currency"], default="none")

    gen = sub.add_parser("generate", help="generate synthetic data only")
    gen.add_argument("--seed", type=int, default=42)
    gen.add_argument("--n-base", type=int, default=150)
    gen.add_argument("--corrupt", choices=["none", "currency"], default="none")

    sub.add_parser("run", help="run the pipeline against already-generated data")

    args = parser.parse_args()

    if args.command == "demo":
        n_l, n_s = generate(seed=args.seed, corrupt=args.corrupt)
        print(f"Generated {n_l} ledger rows, {n_s} settlement rows (corrupt={args.corrupt}).")
        summary = run_pipeline()
        _print_summary(summary)

    elif args.command == "generate":
        n_l, n_s = generate(seed=args.seed, n_base=args.n_base, corrupt=args.corrupt)
        print(f"Generated {n_l} ledger rows, {n_s} settlement rows in data/generated/")

    elif args.command == "run":
        summary = run_pipeline()
        _print_summary(summary)


def _print_summary(summary):
    print("\n=== Reconciliation summary ===")
    print(f"Ledger rows:      {summary['ledger_rows']}")
    print(f"Settlement rows:  {summary['settlement_rows']}")
    print(f"Matched pairs:    {summary['matched_pairs']}")
    print(f"Exceptions:       {summary['exceptions']}")
    print(f"Match rate:       {summary['match_rate'] * 100:.1f}%")
    print(f"Overall accuracy vs ground truth: {(summary['overall_accuracy'] or 0) * 100:.1f}%")
    print("\nPer-category accuracy:")
    for cat, stats in summary["per_category"].items():
        acc = (stats["accuracy"] or 0) * 100
        print(f"  {cat:28s} {stats['correct']:>3}/{stats['total']:<3}  ({acc:.1f}%)")
    print("\nFull report: reports/scorecard.json, reports/matches.csv, reports/exceptions.csv")


if __name__ == "__main__":
    main()
