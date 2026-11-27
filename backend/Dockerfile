FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=2.3.2 \
    POETRY_VIRTUALENVS_CREATE=false \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# poppler-utils: renders scanned PDFs for OCR. tesseract-ocr(-eng): OCR.
# gcc/g++: fallback for any dependency without a prebuilt wheel.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"

COPY pyproject.toml poetry.lock* ./
# torch comes from the CPU-only index (see pyproject.toml), ~3GB smaller.
RUN poetry install --no-interaction --no-ansi --no-root --with ai

# The start script lives outside /app so a bind mount of the source tree
# (dev setups) can never hide it, and CRLF endings from a Windows checkout
# are stripped so "exec /app/startup.sh: no such file" cannot happen.
COPY startup.sh /usr/local/bin/startup.sh
RUN sed -i 's/\r$//' /usr/local/bin/startup.sh && chmod +x /usr/local/bin/startup.sh

COPY . .

RUN adduser --disabled-password --gecos '' appuser \
    && mkdir -p /app/uploads /home/appuser/.cache/huggingface \
    && chown -R appuser:appuser /app /home/appuser
USER appuser
ENV HF_HOME=/home/appuser/.cache/huggingface

EXPOSE 8000

CMD ["/usr/local/bin/startup.sh", "api"]
