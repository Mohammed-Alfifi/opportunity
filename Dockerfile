# حاوية واحدة: الواجهة تُبنى ملفاتٍ ثابتة وتخدمها الخلفية من نفس الأصل
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN rm -f .env.development && npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DATA_DIR=/data STATIC_DIR=/app/web PORT=8000
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=web /web/out ./web
RUN useradd --create-home --uid 10001 forsa && mkdir -p /data && chown forsa /data
USER forsa
EXPOSE 8000
# عامل واحد: حد محاولات الدخول وقفل الجمع في الذاكرة
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --workers 1"]
