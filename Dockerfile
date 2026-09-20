FROM python:3.11-slim
WORKDIR /code

# Single shared image for all Cognify Python services.
# Set via compose build args:
#   SERVICE_NAME = core-backend | ai-service | execution-service
#   SERVICE_PORT = 8000 | 8001 | 8002
ARG SERVICE_NAME=core-backend
ARG SERVICE_PORT=8000

ENV PORT=${SERVICE_PORT} \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/${SERVICE_NAME}/app ./app
# Runtime shared files: the problem bank (bank JSON), all service app dirs
# (core-backend alias-loads ai-service/execution-service modules in-process
# for the student slice), and shared packages (taxonomy / problem-schema).
COPY services ./services
COPY packages ./packages
COPY problem-bank ./problem-bank

EXPOSE ${SERVICE_PORT}
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
