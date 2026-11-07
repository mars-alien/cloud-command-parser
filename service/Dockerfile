FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false HF_HOME=/tmp/hf
WORKDIR /app
COPY service/requirements.txt .
# CPU-only torch wheel (no CUDA libraries) keeps the image well under 2 GB
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu torch==2.5.1+cpu \
 && pip install --no-cache-dir -r requirements.txt
COPY common ./common
COPY service ./service
COPY data/schema.json ./data/schema.json
EXPOSE 8000
CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8000"]
