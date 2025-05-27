# ----------------------------------------
# 1) Build the React app
# ----------------------------------------
FROM node:18-alpine AS ui-build
WORKDIR /app/frontend

# Install only package files first (cache-friendly)
COPY frontend/package*.json ./
RUN npm ci

# Copy the rest of your React source & build production assets
COPY frontend/ ./
RUN npm run build

# ----------------------------------------
# 2) Build the Python container
# ----------------------------------------
FROM python:3.11-slim
WORKDIR /app

# 2a) Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 2b) Copy your backend code (and raw frontend source, if any)
COPY . .  

# 2c) Overlay the compiled React bundle — must come *after* COPY . .
COPY --from=ui-build /app/frontend/build/. ./frontend/build

# 2d) Expose port and start Uvicorn
ENV PORT=8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
