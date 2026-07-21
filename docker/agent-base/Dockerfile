FROM python:3.12-slim

# Base image for dockerized agent runs.
# Install Claude Code CLI when network/auth allow; entrypoint falls back to mock mode.
RUN apt-get update \
    && apt-get install -y --no-install-recommends bash curl ca-certificates git nodejs npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY entrypoint.py /stb/entrypoint.py
RUN chmod +x /stb/entrypoint.py

ENV STB_AGENT=mock
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "/stb/entrypoint.py"]
