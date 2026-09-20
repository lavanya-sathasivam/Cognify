FROM python:3.11-slim
WORKDIR /code

# Single shared image for all Cognify Python services.
ARG SERVICE_NAME=core-backend
ARG SERVICE_PORT=8000

ENV PORT=${SERVICE_PORT} \
    PYTHONUNBUFFERED=1

# Docker CLI is required by execution-service because the
# sandbox runner launches isolated containers through `docker run`.
RUN if [ "$SERVICE_NAME" = "execution-service" ]; then \
      apt-get update && \
      apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg; \
      install -m 0755 -d /etc/apt/keyrings; \
      curl -fsSL https://download.docker.com/linux/debian/gpg \
        -o /etc/apt/keyrings/docker.asc; \
      chmod a+r /etc/apt/keyrings/docker.asc; \
      echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian trixie stable" \
        > /etc/apt/sources.list.d/docker.list; \
      apt-get update; \
      apt-get install -y --no-install-recommends docker-ce-cli; \
      rm -rf /var/lib/apt/lists/*; \
    fi
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/${SERVICE_NAME}/app ./app
COPY services ./services
COPY packages ./packages
COPY problem-bank ./problem-bank

EXPOSE ${SERVICE_PORT}
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port $PORT"]