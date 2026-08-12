FROM python:3.11-slim

WORKDIR /app

# Install system deps for unstructured file parsing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpoppler-cpp-dev \
    tesseract-ocr \
    libreoffice \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create data directories
RUN mkdir -p /app/data/uploads /app/data/crawls

COPY . .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
