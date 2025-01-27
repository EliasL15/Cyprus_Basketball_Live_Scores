# Use official Playwright image as base for browser dependencies
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

# Set the working directory
WORKDIR /app

# Install Python and system dependencies
RUN apt-get update && \
    apt-get install -y \
    python3.11 \
    python3-pip \
    python3.11-venv \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python3.11 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium && \
    playwright install-deps

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Expose port
EXPOSE 8000

# Start application
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "1", "--preload", "--timeout", "120", "--name", "cyprus_scraper"]