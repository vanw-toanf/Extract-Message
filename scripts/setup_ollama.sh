#!/bin/bash
set -e

MODEL=${1:-qwen2.5:3b}

echo "=== Installing Ollama ==="
curl -fsSL https://ollama.com/install.sh | sh

echo "=== Configuring Ollama to listen on 0.0.0.0 ==="
mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/override.conf << 'EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
Environment="OLLAMA_KEEP_ALIVE=-1"
EOF

systemctl daemon-reload
systemctl enable ollama
systemctl restart ollama

echo "=== Waiting for Ollama to start ==="
until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 2
done

echo "=== Pulling $MODEL ==="
ollama pull "$MODEL"

echo ""
echo "Done! Ollama đang chạy tại 0.0.0.0:11434 với model $MODEL"
echo "Kiểm tra: ollama list"
