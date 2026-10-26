# Multi-stage Dockerfile: Builds Next.js frontend, then runs FastAPI all-in-one!
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci || npm install

COPY frontend/ ./
RUN npm run build

# Stage 2: Final All-in-One Python Container
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install backend dependencies
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend code
COPY backend/ ./backend/

# Copy built frontend static assets from Stage 1
COPY --from=frontend-builder /app/frontend/out ./frontend/out/

# Create required storage directories
RUN mkdir -p backend/storage/artifacts backend/storage/templates

ENV PORT=10000
EXPOSE 10000

WORKDIR /app/backend
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
