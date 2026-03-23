FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/relatorios /app/cache

ENV CACHE_DIR=/app/cache

ENTRYPOINT ["python", "main.py"]
CMD ["--sem-email", "--sem-supabase"]
