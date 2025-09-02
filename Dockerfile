# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip to latest version to avoid warnings
RUN pip install --upgrade pip

# Copy requirements first to leverage Docker cache
COPY src/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Generate Prisma client during build
RUN python -m prisma generate --schema=./prisma/schema.prisma

# Expose the port the app runs on
EXPOSE 8000

# Make the startup script executable
RUN chmod +x ./startup.py

# Command to run the application
CMD ["python", "startup.py"]
