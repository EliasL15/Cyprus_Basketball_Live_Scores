# Use official Playwright image as base for browser dependencies (or switch to a lighter base if you prefer)
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

# Copy dependency file first for better cache performance
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Start application with gunicorn
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--timeout", "120"]