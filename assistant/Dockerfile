FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WORKSPACE=/data/workspace

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY web ./web

# Hugging Face Spaces chay bang user khong phai root -> can thu muc ghi duoc.
RUN mkdir -p /data/workspace && chmod -R 777 /data

EXPOSE 7860

# PORT do host cap phat (Render, Railway, Fly...); 7860 la mac dinh cua HF Spaces.
CMD ["sh", "-c", "uvicorn app.server:app --host 0.0.0.0 --port ${PORT:-7860}"]
