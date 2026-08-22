"""Pushes the trained model to the Hugging Face Hub.

Run: python -m ml.push_to_huggingface <your-username>/<repo-name>

Requires your own Hugging Face account and token -- this script never
runs automatically and is never invoked by anything else in this project.
Log in first (one of):

    huggingface-cli login
    # or set the HF_TOKEN environment variable

This uploads model.skops (safe serialization, no pickle) and MODEL_CARD.md
(the repo's README.md) to a new or existing model repo. It does not train
anything -- run `python -m ml.train` first if model.skops doesn't exist
yet or you want to push a freshly retrained version.
"""
import argparse
import sys
from pathlib import Path

MODEL_PATH = Path(__file__).resolve().parent / "model.skops"
MODEL_CARD_PATH = Path(__file__).resolve().parent / "MODEL_CARD.md"
TRAINING_REPORT_PATH = Path(__file__).resolve().parent / "training_report.json"


def push(repo_id, private=False):
    from huggingface_hub import HfApi

    if not MODEL_PATH.exists():
        print(f"No trained model found at {MODEL_PATH}. Run `python -m ml.train` first.", file=sys.stderr)
        sys.exit(1)

    api = HfApi()
    print(f"Creating (or reusing) repo: {repo_id}")
    api.create_repo(repo_id, repo_type="model", private=private, exist_ok=True)

    print("Uploading model.skops...")
    api.upload_file(path_or_fileobj=str(MODEL_PATH), path_in_repo="model.skops", repo_id=repo_id, repo_type="model")

    print("Uploading model card as README.md...")
    api.upload_file(path_or_fileobj=str(MODEL_CARD_PATH), path_in_repo="README.md", repo_id=repo_id, repo_type="model")

    if TRAINING_REPORT_PATH.exists():
        print("Uploading training_report.json...")
        api.upload_file(
            path_or_fileobj=str(TRAINING_REPORT_PATH), path_in_repo="training_report.json",
            repo_id=repo_id, repo_type="model",
        )

    print(f"\nDone: https://huggingface.co/{repo_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Push the trained match classifier to the Hugging Face Hub.")
    parser.add_argument("repo_id", help="e.g. your-username/ledger-match-classifier")
    parser.add_argument("--private", action="store_true", help="create the repo as private")
    args = parser.parse_args()
    push(args.repo_id, private=args.private)
