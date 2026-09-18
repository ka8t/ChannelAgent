# ChannelAgent runtime image (#18).
#
# python:3.12-slim, not the newest interpreter, so every dependency
# here (langgraph, sqlalchemy, cryptography's compiled extension) has a
# prebuilt wheel available — avoids source builds inside the image.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Real data (SQLite file) lives here — mount a volume over it in
# docker-compose.yml so it survives container recreation.
RUN mkdir -p /app/data

CMD ["python", "-m", "app.main"]
