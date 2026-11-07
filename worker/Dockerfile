FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir boto3==1.35.70
COPY common ./common
COPY worker ./worker
COPY prompts ./prompts
CMD ["python", "-m", "worker.worker"]
