FROM python:3.12.11-slim
WORKDIR /app
RUN apt-get update \
    && apt-get install --no-install-recommends -y tesseract-ocr=5.5.0-1+b1 tesseract-ocr-eng=1:4.1.0-2 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
