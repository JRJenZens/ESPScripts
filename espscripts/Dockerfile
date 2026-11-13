FROM python:3.13-alpine
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py catalog.json ./
COPY web ./web
ENV ESPSCRIPTS_DB=/data/espscripts.sqlite3
CMD ["gunicorn", "--bind", "0.0.0.0:8099", "--workers", "1", "--threads", "4", "--access-logfile", "-", "app:app"]
