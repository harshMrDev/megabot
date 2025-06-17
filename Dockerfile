FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy Python dependencies first for caching
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the bot code
COPY . .

# Set environment variables for UTF-8 support and unbuffered output
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

# Expose no ports (Telegram bots don't need it, but you can EXPOSE 8080 if using webhooks)
# EXPOSE 8080

# Run the bot
CMD ["python", "main.py"]