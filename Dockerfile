# Project 6: same pattern as Projects 1-5 (python slim image, uvicorn, ECS Fargate).
FROM python:3.12-slim

WORKDIR /app

COPY requirements-service.txt .
RUN pip install --no-cache-dir -r requirements-service.txt

COPY src/ ./src/
COPY static/ ./static/
COPY data/demo_samples.json ./data/demo_samples.json

# Run as a normal user, not root. results/ holds the demo worksheets; they are temporary.
RUN useradd --create-home app && mkdir -p results && chown -R app:app /app
USER app

# The ANTHROPIC_API_KEY is NOT baked in. It is injected at run time (AWS Secrets Manager via the
# ECS task definition, or `-e ANTHROPIC_API_KEY=...` for a local test). Without it, uploads are
# switched off and the sample bills still work.
#
# Uploaded bills must not be written to disk: the reply cache is switched off in the container.
# P6_MAX_LIVE_CALLS is a hard stop on API calls per container run (a bill uses about 2 calls).
ENV P6_NO_CACHE=1 \
    P6_MAX_LIVE_CALLS=300 \
    P6_DEMO_PER_IP_HOUR=5 \
    P6_DEMO_PER_DAY=50 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)"

CMD ["uvicorn", "src.service:app", "--host", "0.0.0.0", "--port", "8000"]




