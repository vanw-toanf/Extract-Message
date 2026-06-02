#!/usr/bin/env bash
# Run on training server (24GB VRAM) to install deps and download model.
# Usage: bash setup.sh
set -e

CONDA_ENV="py3.12"
MODEL_DIR="../../models/Qwen2.5-7B-Instruct"

echo "=== 0. Activate conda env: $CONDA_ENV ==="
source /home/vanwtoanf/miniconda3/etc/profile.d/conda.sh
conda activate "$CONDA_ENV"
echo "Python: $(which python)"

echo "=== 1. Install LLaMA-Factory ==="
pip install -q "llamafactory[torch,metrics]"

echo "=== 2. Download Qwen2.5-7B-Instruct from HuggingFace ==="
if [ ! -d "$MODEL_DIR" ]; then
    pip install -q huggingface_hub[cli]
    hf download Qwen/Qwen2.5-7B-Instruct \
        --local-dir "$MODEL_DIR" \
        --exclude "*.bin"          # prefer safetensors
    echo "Model saved to $MODEL_DIR"
else
    echo "Model already exists at $MODEL_DIR, skipping download."
fi

echo "=== 3. Copy dataset_info.json to LLaMA-Factory data dir ==="
# LLaMA-Factory reads dataset_info.json from its own data/ folder OR
# from the path specified in --dataset_dir. We put it next to our data.
cp dataset_info.json ../../data/finetune/qwen_sft/dataset_info.json

echo ""
echo "Done. Run training with:"
echo "  llamafactory-cli train train.yaml"
