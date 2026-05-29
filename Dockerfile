FROM python:3.12-slim AS builder

RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 300 --retries 5 \
    torch torchvision --index-url https://download.pytorch.org/whl/cpu

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 300 --retries 5 easyocr==1.7.2

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 300 --retries 5 \
    fastapi==0.118.0 "uvicorn[standard]==0.37.0" pydantic==2.11.7 \
    python-dotenv==1.1.0 requests==2.33.1 rapidfuzz==3.13.0 \
    openai==2.30.0 python-multipart==0.0.20 pillow==12.0.0

FROM python:3.12-slim AS runtime

COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
