#!/bin/bash
# Setup Ollama trên server và đăng ký finetuned model từ file GGUF local.
# Usage:
#   bash setup_ollama.sh                          # chỉ cài Ollama
#   bash setup_ollama.sh models/vin.gguf          # cài + tạo model vin-extractor
set -e

GGUF_PATH=${1:-}
MODEL_NAME="vin-extractor"
MODELFILE_PATH="models/Modelfile"

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

if [ -z "$GGUF_PATH" ]; then
    echo ""
    echo "Ollama đã chạy. Chưa tạo model vì chưa chỉ định file GGUF."
    echo "Chạy lại với: bash setup_ollama.sh <đường_dẫn_tới_file.gguf>"
    exit 0
fi

if [ ! -f "$GGUF_PATH" ]; then
    echo "ERROR: Không tìm thấy file GGUF: $GGUF_PATH"
    exit 1
fi

GGUF_ABS=$(realpath "$GGUF_PATH")
echo "=== Tạo Modelfile tại $MODELFILE_PATH ==="
mkdir -p "$(dirname "$MODELFILE_PATH")"
cat > "$MODELFILE_PATH" << MODELEOF
FROM $GGUF_ABS

SYSTEM """Bạn là bộ trích xuất đơn giao hàng Việt Nam.
Chỉ trả về đúng một JSON hợp lệ theo schema đã học, không giải thích.
Số điện thoại hợp lệ đã được thay bằng [PHONE]. Không khôi phục số thật.
Không bịa dữ liệu thiếu. Trường không có hoặc không chắc chắn phải là null.
address_raw giữ nguyên phần địa chỉ trong input.
address_info chỉ mô tả các thành phần địa chỉ thô có trong input, chưa chuẩn hóa địa giới.
Với địa chỉ cũ 3 cấp: neighborhood=xã/phường cũ, municipality=huyện/quận cũ, sub_region=tỉnh/thành cũ.
Với địa chỉ mới 2 cấp: neighborhood=null, municipality=xã/phường mới, sub_region=tỉnh/thành mới.
country là VNM khi có địa chỉ, nếu không có địa chỉ thì null."""

PARAMETER temperature 0
PARAMETER num_ctx 1024
MODELEOF

echo "=== Tạo model '$MODEL_NAME' trong Ollama ==="
ollama create "$MODEL_NAME" -f "$MODELFILE_PATH"

echo ""
echo "Done! Kiểm tra:"
echo "  ollama list"
echo "  ollama run $MODEL_NAME 'khách anh Minh 0912345678, giao 123 Lê Lợi, P.Bến Nghé, Q.1, TP.HCM'"
