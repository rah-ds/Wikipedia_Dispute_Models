#!/usr/bin/env python3
"""
download_gemma4.py — Download Gemma 4 model weights from HuggingFace Hub

Downloads model weights to a local cache directory suitable for both
local development and Rivanna HPC scratch/project storage.  On Rivanna,
point --cache-dir at /scratch/<YOUR_COMPUTE_ID>/models/ so the weights
persist between SLURM jobs without re-downloading.

Usage
-----
  # Local (tokens from HF_TOKEN env var)
  python scripts/download_gemma4.py

  # Specific size / output dir
  python scripts/download_gemma4.py --model google/gemma-4-9b-it
  python scripts/download_gemma4.py --model google/gemma-4-27b-it \\
      --cache-dir /scratch/YOUR_COMPUTE_ID/models

  # Verify an already-downloaded model
  python scripts/download_gemma4.py --verify --cache-dir /scratch/YOUR_COMPUTE_ID/models

Requirements
------------
  pip install transformers torch huggingface_hub
  export HF_TOKEN=hf_YOUR_TOKEN_HERE   # Gemma is a gated model
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Optional deps
# ─────────────────────────────────────────────────────────────────────────────

try:
    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import RepositoryNotFoundError, GatedRepoError

    HF_HUB_AVAILABLE = True
except ImportError:
    HF_HUB_AVAILABLE = False
    print(
        "ERROR: 'huggingface_hub' not installed.\n"
        "       Run: pip install huggingface_hub transformers torch\n"
    )
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Constants — update model ID once Gemma 4 HF page is confirmed
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Replace with the confirmed HuggingFace model ID when Gemma 4 is
#       available on the Hub.  Common candidates:
#         google/gemma-4-9b-it   (instruction-tuned, 9B params)
#         google/gemma-4-27b-it  (instruction-tuned, 27B params)
DEFAULT_MODEL_ID = "google/gemma-4-9b-it"

# Approximate VRAM requirements (fp16 weights) — for choosing instance type
VRAM_ESTIMATES = {
    "google/gemma-4-1b-it": "~2 GB",
    "google/gemma-4-4b-it": "~8 GB",
    "google/gemma-4-9b-it": "~18 GB",
    "google/gemma-4-27b-it": "~54 GB  (consider 4-bit quant or multi-GPU)",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def get_token() -> str | None:
    """Return HF token from env or ~/.huggingface/token file."""
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if token:
        return token
    token_file = Path.home() / ".huggingface" / "token"
    if token_file.exists():
        return token_file.read_text().strip() or None
    return None


def pretty_size(path: Path) -> str:
    """Return human-readable total size of a directory tree."""
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if total < 1024:
            return f"{total:.1f} {unit}"
        total /= 1024
    return f"{total:.1f} PB"


def verify_download(model_id: str, cache_dir: Path) -> bool:
    """Check that the expected model files are present in cache_dir."""
    local_path = cache_dir / model_id.replace("/", "--")
    # snapshot_download stores files under models--<org>--<name>/snapshots/...
    snapshots = list(local_path.glob("snapshots/*"))
    if not snapshots:
        # Also check for a flat layout (manual download)
        flat_config = cache_dir / "config.json"
        if flat_config.exists():
            print(f"  Found flat layout at {cache_dir}")
            return True
        print(f"  No snapshots found under {local_path}")
        return False

    snap = snapshots[0]
    required = ["config.json", "tokenizer.json"]
    missing = [f for f in required if not (snap / f).exists()]
    if missing:
        print(f"  Missing files: {missing}")
        return False

    weight_files = list(snap.glob("*.safetensors")) + list(snap.glob("*.bin"))
    if not weight_files:
        print("  No weight files (.safetensors / .bin) found")
        return False

    print(f"  Snapshot: {snap}")
    print(f"  Weight shards: {len(weight_files)}")
    print(f"  Total size on disk: {pretty_size(snap)}")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Core download
# ─────────────────────────────────────────────────────────────────────────────


def download_model(model_id: str, cache_dir: Path, token: str | None) -> Path:
    """Download all model files via huggingface_hub.snapshot_download."""
    cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nDownloading  : {model_id}")
    print(f"Cache dir    : {cache_dir}")
    if model_id in VRAM_ESTIMATES:
        print(f"VRAM needed  : {VRAM_ESTIMATES[model_id]}")
    if not token:
        print(
            "\nWARNING: No HF_TOKEN found — Gemma is a gated model and will\n"
            "         likely fail without authentication.  Set:\n"
            "           export HF_TOKEN=hf_YOUR_TOKEN_HERE\n"
            "         Obtain a token at https://huggingface.co/settings/tokens\n"
            "         and accept the Gemma licence at the model page.\n"
        )

    try:
        local_dir = snapshot_download(
            repo_id=model_id,
            cache_dir=str(cache_dir),
            token=token,
            ignore_patterns=["*.msgpack", "flax_model*", "tf_model*", "rust_model*"],
        )
    except GatedRepoError:
        print(
            "\nERROR: Access denied — this is a gated model.\n"
            "       1. Accept the licence at https://huggingface.co/<model>\n"
            "       2. Set HF_TOKEN=hf_YOUR_TOKEN_HERE\n"
        )
        sys.exit(1)
    except RepositoryNotFoundError:
        print(
            f"\nERROR: Model '{model_id}' not found on HuggingFace.\n"
            "       Check the model ID (Gemma 4 may not be public yet).\n"
            "       Known candidates: " + ", ".join(VRAM_ESTIMATES.keys()) + "\n"
        )
        sys.exit(1)

    print(f"\nDownload complete → {local_dir}")
    return Path(local_dir)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Download Gemma 4 model weights from HuggingFace Hub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--model",
        default=DEFAULT_MODEL_ID,
        metavar="REPO_ID",
        help=f"HuggingFace model repo (default: {DEFAULT_MODEL_ID})",
    )
    p.add_argument(
        "--cache-dir",
        default="models/gemma4",
        metavar="DIR",
        help=(
            "Local directory to store weights.  "
            "On Rivanna use /scratch/YOUR_COMPUTE_ID/models  (default: models/gemma4)"
        ),
    )
    p.add_argument(
        "--token",
        default=None,
        metavar="HF_TOKEN",
        help="HuggingFace access token (overrides HF_TOKEN env var)",
    )
    p.add_argument(
        "--verify",
        action="store_true",
        help="Only verify an existing download, do not fetch",
    )
    p.add_argument(
        "--list-sizes",
        action="store_true",
        help="Print available Gemma 4 size variants and exit",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.list_sizes:
        print("\nKnown Gemma 4 variants (VRAM estimates for fp16):")
        for name, vram in VRAM_ESTIMATES.items():
            print(f"  {name:<35}  {vram}")
        print()
        return

    cache_dir = Path(args.cache_dir).expanduser().resolve()
    token = args.token or get_token()

    if args.verify:
        print(f"\nVerifying {args.model} in {cache_dir} ...")
        ok = verify_download(args.model, cache_dir)
        if ok:
            print("  Verification passed.")
        else:
            print("  Verification FAILED — run without --verify to download.")
            sys.exit(1)
        return

    local_dir = download_model(args.model, cache_dir, token)

    print("\nVerifying download ...")
    ok = verify_download(args.model, cache_dir)
    if ok:
        print("  OK\n")
    else:
        print("  WARNING: verification step failed — check the files above.\n")

    print("Next steps:")
    print(f"  Local test  : python scripts/gemma4_bpmn.py --model-dir {local_dir}")
    print(
        f"  Rivanna job : edit scripts/rivanna_gemma4.slurm → set MODEL_DIR={local_dir}"
    )


if __name__ == "__main__":
    main()
