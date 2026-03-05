FROM python:3.12-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e ".[dev]"

CMD ["pytest", "tests/test_docker_integration.py", "-v", "--tb=short"]
