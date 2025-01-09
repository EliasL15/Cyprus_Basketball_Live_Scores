# Base Python image
FROM python:3.11-slim

# Install required system dependencies
RUN apt-get update && apt-get install -y \
    libgstreamer-gl1.0-0 \
    gstreamer1.0-plugins-bad \
    libavif15 \
    libenchant-2-2 \
    libsecret-1-0 \
    libmanette-0.2-0 \
    libgles2-mesa && \
    apt-get clean

# Set the working directory
WORKDIR /app

# Copy project files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install

# Expose the port your application will run on
EXPOSE 8000

# Start the application
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000"]
