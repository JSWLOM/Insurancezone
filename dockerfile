# ── Insurance Zone API — Dockerfile ──────────────────────────
# Python 3.11 slim keeps the image small (~150MB vs ~900MB full)
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# Copy requirements first — Docker caches this layer separately.
# If requirements.txt doesn't change, pip install is skipped on rebuilds.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Koyeb routes external traffic to port 8000 by default
EXPOSE 8000

# Start the FastAPI app with Uvicorn
# --host 0.0.0.0  → accept connections from outside the container
# --port 8000     → match the EXPOSE above
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]