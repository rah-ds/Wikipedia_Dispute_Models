#!/bin/bash
# =============================================================================
# rivanna_gemma4.slurm — Gemma 4 BPMN generation job for UVA Rivanna HPC
#
# Submits a GPU job that:
#   1. Activates your conda/uv environment
#   2. Runs gemma4_bpmn.py over a batch of dispute text files
#   3. Writes .bpmn + .json outputs to $SCRATCH/bpmn_out/
#
# Submit
# ------
#   sbatch scripts/rivanna_gemma4.slurm
#
# Monitor
# -------
#   squeue -u $USER
#   tail -f logs/gemma4_bpmn_%j.out
#
# Useful Rivanna docs
# -------------------
#   https://www.rc.virginia.edu/userinfo/rivanna/slurm/
#   https://www.rc.virginia.edu/userinfo/rivanna/software/pytorch/
# =============================================================================

# ── SLURM directives ──────────────────────────────────────────────────────────

#SBATCH --job-name=gemma4_bpmn
#SBATCH --account=shakeri_ds6050          # UVA DS6050 allocation
#SBATCH --partition=gpu                  # gpu  |  bii-gpu  |  standard
#SBATCH --gres=gpu:a100:1               # A100 40 GB fits gemma-4-9b-it in fp16
                                         # Use gpu:a100:2 for 27B model
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G                        # system RAM (not VRAM)
#SBATCH --time=04:00:00                  # wall-clock limit HH:MM:SS
#SBATCH --output=logs/gemma4_bpmn_%j.out
#SBATCH --error=logs/gemma4_bpmn_%j.err
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --mail-user=rah5ff@virginia.edu

# ── Environment ───────────────────────────────────────────────────────────────

# TODO: Confirm exact module versions with `module spider cuda` on Rivanna
module purge
module load cuda/12.4.1                  # or whichever CUDA is available
module load miniforge/24.3.0-py3.11     # or anaconda/2023.07-py3.11

# ── Paths — edit before submitting ───────────────────────────────────────────

# Root of this repository on Rivanna
PROJECT_DIR="$HOME/Wikipedia_Dispute_Models"   # TODO: adjust to your path

# Where model weights live (use scratch for large files)
MODEL_DIR="/scratch/$USER/models/gemma4/google/gemma-4-9b-it"  # set by download script

# Input: directory of *.txt dispute files to process
INPUT_DIR="$PROJECT_DIR/data/raw/drn"          # TODO: adjust to your input dir

# Output directory for .bpmn and .json files
OUTPUT_DIR="/scratch/$USER/bpmn_out"

# Conda environment name (created during setup)
CONDA_ENV="wikipedia_dispute"                   # TODO: adjust if different

# HuggingFace token (only needed if MODEL_DIR doesn't exist yet)
# export HF_TOKEN=hf_YOUR_TOKEN_HERE           # TODO: uncomment and set if needed
#   Better: store in ~/.bashrc or Rivanna secrets and load here
#   Do NOT commit the token to git

# ── Activate environment ─────────────────────────────────────────────────────

cd "$PROJECT_DIR" || { echo "ERROR: PROJECT_DIR not found: $PROJECT_DIR"; exit 1; }

# Activate conda environment
source activate "$CONDA_ENV" || conda activate "$CONDA_ENV" || {
    echo "ERROR: Could not activate conda env '$CONDA_ENV'"
    echo "       Create it first:  conda create -n $CONDA_ENV python=3.11"
    echo "       Then:             pip install transformers torch accelerate bitsandbytes"
    exit 1
}

# ── Pre-flight checks ─────────────────────────────────────────────────────────

echo "=========================================="
echo "Job ID       : $SLURM_JOB_ID"
echo "Node         : $SLURMD_NODENAME"
echo "GPU(s)       : $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || echo 'N/A')"
echo "Python       : $(python --version)"
echo "Project dir  : $PROJECT_DIR"
echo "Model dir    : $MODEL_DIR"
echo "Input dir    : $INPUT_DIR"
echo "Output dir   : $OUTPUT_DIR"
echo "=========================================="

# Download model if not already cached
if [ ! -d "$MODEL_DIR" ]; then
    echo "Model not found at $MODEL_DIR — downloading ..."
    python scripts/download_gemma4.py \
        --model google/gemma-4-9b-it \
        --cache-dir "/scratch/$USER/models/gemma4"
fi

mkdir -p "$OUTPUT_DIR"
mkdir -p logs

# ── Run BPMN generation ───────────────────────────────────────────────────────

export MODEL_DIR          # picked up by gemma4_bpmn.py
export TOKENIZERS_PARALLELISM=false   # avoid tokenizer warning with multiprocessing

echo ""
echo "Starting BPMN generation ..."
echo ""

python scripts/gemma4_bpmn.py \
    --batch "$INPUT_DIR" \
    --venue drn \
    --output-dir "$OUTPUT_DIR" \
    --model-dir "$MODEL_DIR" \
    --max-tokens 1024

EXIT_CODE=$?

echo ""
echo "=========================================="
echo "Job finished with exit code: $EXIT_CODE"
echo "Output files in: $OUTPUT_DIR"
ls -lh "$OUTPUT_DIR" 2>/dev/null | tail -20
echo "=========================================="

exit $EXIT_CODE

# =============================================================================
# QUICK REFERENCE — common Rivanna GPU partitions
# =============================================================================
#
# Partition    GPUs available        Notes
# ----------   ------------------    -------------------------------------------
# gpu          A100 40GB, V100 32GB  General GPU queue; use for most jobs
# bii-gpu      A100 80GB             Bioinformatics allocation; large models
# standard     CPU only              No GPU; not suitable for this script
#
# Request specific GPU type:
#   --gres=gpu:a100:1    → A100 40GB (fits gemma-4-9b-it fp16)
#   --gres=gpu:v100:1    → V100 32GB (use --quantize 8bit for 9B model)
#   --gres=gpu:a100:2    → two A100s (fits gemma-4-27b-it fp16)
#
# Check available GPUs:
#   sinfo -p gpu --format="%N %G %m"
#
# Interactive GPU session (useful for debugging):
#   ijob -A YOUR_ALLOCATION -p gpu --gres=gpu:a100:1 --mem=32G -c 8
#
# =============================================================================
# SETUP CHECKLIST (do once before first sbatch)
# =============================================================================
#
#  1. SSH to Rivanna:
#       ssh YOUR_COMPUTING_ID@rivanna.hpc.virginia.edu
#
#  2. Clone the repo to $HOME (or /project/YOUR_ALLOCATION/):
#       git clone https://github.com/YOUR_ORG/Wikipedia_Dispute_Models.git
#       cd Wikipedia_Dispute_Models
#
#  3. Create conda environment:
#       module load miniforge/24.3.0-py3.11
#       conda create -n wikipedia_dispute python=3.11 -y
#       conda activate wikipedia_dispute
#       pip install transformers torch accelerate bitsandbytes huggingface_hub
#       pip install -e ".[dev]"       # installs project itself
#
#  4. Download model weights to scratch (fast storage):
#       export HF_TOKEN=hf_YOUR_TOKEN_HERE
#       python scripts/download_gemma4.py \
#           --model google/gemma-4-9b-it \
#           --cache-dir /scratch/$USER/models/gemma4
#
#  5. Copy or symlink your dispute text files to data/raw/ if not already there
#
#  6. Submit:
#       sbatch scripts/rivanna_gemma4.slurm
#
# =============================================================================
