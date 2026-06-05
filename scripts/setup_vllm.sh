#!/usr/bin/env bash
# Cài vLLM và đăng ký systemd service trên T4 server.
# Usage: bash setup_vllm.sh
# Yêu cầu: AWQ model đã có tại models/qwen25_7b_awq_int4/
set -e

MODEL_PATH="$(pwd)/models/qwen25_7b_awq_int4"
VENV_PYTHON="$(pwd)/.venv/bin/python"
VENV_PIP="$(pwd)/.venv/bin/pip"
RUN_SCRIPT="$(pwd)/scripts/run_vllm.sh"
SERVICE_NAME="vllm-vin"

echo "=== 1. Kiểm tra model ==="
if [ ! -d "$MODEL_PATH" ]; then
    echo "ERROR: Không tìm thấy model tại $MODEL_PATH"
    exit 1
fi
echo "Model OK: $MODEL_PATH"

echo "=== 2. Install vLLM 0.8.5 + torch CUDA ==="
# torch CUDA trước để tránh CPU-only version
$VENV_PIP install torch==2.7.0+cu126 --index-url https://download.pytorch.org/whl/cu126 -q
$VENV_PIP install "vllm==0.8.5" -q
$VENV_PIP install "transformers==4.51.3" -q
echo "vLLM: $($VENV_PYTHON -c 'import vllm; print(vllm.__version__)')"

echo "=== 3. Fix tokenizer_config.json (extra_special_tokens list→dict) ==="
$VENV_PYTHON - << 'PYEOF'
import json, shutil, sys
path = sys.argv[1] if len(sys.argv) > 1 else "models/qwen25_7b_awq_int4/tokenizer_config.json"
tc = json.load(open(path))
if isinstance(tc.get("extra_special_tokens"), list):
    shutil.copy(path, path + ".bak")
    tc["extra_special_tokens"] = {}
    json.dump(tc, open(path, "w"), ensure_ascii=False, indent=2)
    print("Fixed extra_special_tokens: list → {}")
else:
    print("extra_special_tokens already OK")
PYEOF

echo "=== 4. Tạo wrapper script ==="
cat > "$RUN_SCRIPT" << SCRIPT
#!/bin/bash
export CUDA_VISIBLE_DEVICES=0
export VLLM_USE_FLASHINFER_SAMPLER=0
export VLLM_ATTENTION_BACKEND=TRITON
export PATH=$(pwd)/.venv/bin:/usr/local/cuda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

exec $VENV_PYTHON \\
    -m vllm.entrypoints.openai.api_server \\
    --model $MODEL_PATH \\
    --quantization awq \\
    --dtype float16 \\
    --max-model-len 1024 \\
    --max-num-seqs 20 \\
    --gpu-memory-utilization 0.85 \\
    --swap-space 0 \\
    --no-enable-chunked-prefill \\
    --block-size 32 \\
    --host 0.0.0.0 \\
    --port 8001 \\
    --served-model-name vin-extractor
SCRIPT
chmod +x "$RUN_SCRIPT"

echo "=== 5. Tạo systemd service ==="
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null << EOF
[Unit]
Description=vLLM OpenAI-compatible server (vin-extractor AWQ INT4)
After=network.target

[Service]
User=vanwtoanf
WorkingDirectory=$(pwd)
ExecStart=${RUN_SCRIPT}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
sudo systemctl start ${SERVICE_NAME}

echo ""
echo "=== 6. Chờ vLLM khởi động (~120s) ==="
for i in $(seq 1 60); do
    if journalctl -u ${SERVICE_NAME} -n 3 --no-pager --output=cat 2>/dev/null | grep -q "startup complete"; then
        echo "vLLM sẵn sàng!"
        curl -s http://localhost:8001/v1/models | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"][0]["id"])' 2>/dev/null
        break
    fi
    sleep 2
    echo -n "."
done

echo ""
echo "Done. Kiểm tra:"
echo "  systemctl status ${SERVICE_NAME}"
echo "  curl http://localhost:8001/v1/models"
