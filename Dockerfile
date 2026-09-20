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
# Alembic migrations (#11) — app/db/session.py's init_db() runs these
# at startup, so both must be present in the image, not just alembic
# the Python package.
COPY alembic.ini .
COPY alembic/ ./alembic/

# Real data (SQLite file) lives here — mount a volume over it in
# docker-compose.yml so it survives container recreation.
RUN mkdir -p /app/data

# Inside the container the Admin API must listen on every interface or the
# published port cannot reach it. What is exposed to the outside is decided
# by the port mapping in docker-compose.yml (loopback by default, #52).
ENV API_SERVER_HOST=0.0.0.0

CMD ["python", "-m", "app.main"]
