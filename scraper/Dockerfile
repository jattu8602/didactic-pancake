FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    wget curl gnupg \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    libatspi2.0-0 libwayland-client0 libxshmfence1 \
    --no-install-recommends && rm -rf /var/lib/apt/lists/*

ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers

RUN pip install --no-cache-dir playwright && \
    python3 -m playwright install chromium

WORKDIR /app

# The scraped output will be mounted at /output
VOLUME /output

COPY scrape_generic.py scrape_tripura.py .

ENTRYPOINT ["python3", "scrape_generic.py"]
