FROM python:3.11-slim

WORKDIR /app

# Create data directory for SQLite database
RUN mkdir -p /app/data

# Install system dependencies for pyatv (mDNS/Bonjour), build tools, and ffmpeg for stream merge
RUN apt-get update && apt-get install -y \
    avahi-daemon \
    avahi-utils \
    libavahi-compat-libdnssd1 \
    build-essential \
    g++ \
    make \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
