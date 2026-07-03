FROM python:3.11-slim

WORKDIR /app

# Install system deps for Playwright/Chromium
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium for Playwright + all system deps
RUN python3 -m playwright install chromium && \
    python3 -m playwright install-deps chromium

# Copy scraper code
COPY scraper.py .
COPY combine.py .

# Data dirs (mount these as volumes at runtime)
RUN mkdir -p /data/scraped /output

ENTRYPOINT ["python3", "scraper.py"]
CMD ["--help"]
