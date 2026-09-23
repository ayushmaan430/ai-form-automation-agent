# Official Microsoft Playwright image with pre-installed Chromium & system dependencies
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

# Ensure Python output is unbuffered and browser runs headless in container
ENV PYTHONUNBUFFERED=1 \
    HEADLESS=true \
    PORT=8000

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and HTML forms
COPY . .

# Expose port (Render automatically maps this via $PORT)
EXPOSE 8000

# Start server using the port assigned dynamically by Render ($PORT)
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
