# syntax=docker/dockerfile:1
# Stage 1: build llama-cpp-python + all deps
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake ninja-build && \
    rm -rf /var/lib/apt/lists/*

RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

COPY requirements.txt .

# CPU-only torch (~220MB vs 532MB CUDA wheel)
# cache mount giữ lại packages đã tải, không tải lại nếu fail
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 300 --retries 5 \
    torch torchvision --index-url https://download.pytorch.org/whl/cpu

# easyocr riêng vì deps nặng (opencv, scipy...)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 300 --retries 5 easyocr==1.7.2

# Các deps nhẹ còn lại
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 300 --retries 5 \
    fastapi==0.118.0 "uvicorn[standard]==0.37.0" pydantic==2.11.7 \
    python-dotenv==1.1.0 requests==2.33.1 rapidfuzz==3.13.0 \
    openai==2.30.0 python-multipart==0.0.20 pillow==12.0.0

# Build llama-cpp-python với AVX2/FMA/F16C, tắt curl (không cần SSL)
RUN --mount=type=cache,target=/root/.cache/pip \
    CMAKE_ARGS="-DGGML_AVX2=on -DGGML_F16C=on -DGGML_FMA=on -DLLAMA_CURL=OFF" \
    pip install --timeout 300 --retries 5 llama-cpp-python

# Stage 2: lean runtime image
FROM python:3.12-slim AS runtime

# libgomp1: OpenMP runtime cho llama.cpp multi-thread
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
