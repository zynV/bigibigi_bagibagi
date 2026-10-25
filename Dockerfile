FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    groupadd -r budget && useradd -r -g budget -d /app budget
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
RUN mkdir -p /app/data /app/backups && chown -R budget:budget /app
USER budget
CMD ["sh", "-c", "alembic upgrade head && python -m app.main"]
