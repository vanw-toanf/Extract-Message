#!/usr/bin/env bash
# Cài vLLM và đăng ký systemd service trên T4 server.
# Usage: bash setup_vllm.sh
set -e

MODEL_PATH="$(pwd)/models/qwen25_7b_awq_int4"
VENV_PYTHON="/home/vanwtoanf/Extract-Message/.venv/bin/python"
SERVICE_NAME="vllm-vin"

echo "=== 1. Install vLLM ==="
pip install vllm

echo "=== 2. Kiểm tra model ==="
if [ ! -d "$MODEL_PATH" ]; then
    echo "ERROR: Không tìm thấy model tại $MODEL_PATH"
    exit 1
fi
echo "Model OK: $MODEL_PATH"

echo "=== 3. Tạo systemd service ==="
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null << EOF
[Unit]
Description=vLLM OpenAI-compatible server (vin-extractor AWQ INT4)
After=network.target

[Service]
User=vanwtoanf
WorkingDirectory=/home/vanwtoanf/Extract-Message
ExecStart=${VENV_PYTHON} -m vllm.entrypoints.openai.api_server \\
    --model ${MODEL_PATH} \\
    --quantization awq \\
    --max-model-len 1024 \\
    --max-num-seqs 20 \\
    --gpu-memory-utilization 0.85 \\
    --port 8001 \\
    --served-model-name vin-extractor
Restart=on-failure
RestartSec=10
Environment="CUDA_VISIBLE_DEVICES=0"

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
sudo systemctl start ${SERVICE_NAME}

echo ""
echo "=== 4. Chờ vLLM khởi động (~30s) ==="
for i in $(seq 1 30); do
    if curl -s http://localhost:8001/health > /dev/null 2>&1; then
        echo "vLLM sẵn sàng!"
        break
    fi
    sleep 2
    echo -n "."
done

echo ""
echo "Done. Kiểm tra:"
echo "  systemctl status ${SERVICE_NAME}"
echo "  curl http://localhost:8001/v1/models"
