# Lucida, as a single container.
#
# One process, on purpose. The approval gates and the run lock live in this
# process's memory, and every shop's data is a SQLite file on disk — so this
# scales up (a bigger machine) rather than out (more copies). Two copies would
# hand one owner two different sessions and let two graph runs write over each
# other, which is worse than being slow.

FROM python:3.12-slim

# libgomp is needed by the embedding model the semantic memory uses; curl is
# what the platform health check calls.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so a code change does not reinstall the whole stack.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The business lives here. Mount a volume at this path or a deploy wipes it.
ENV LUCIDA_DATA_DIR=/data
RUN mkdir -p /data

# Cookies are only marked Secure when the app knows it is behind TLS, which
# every one of these hosts terminates for us.
ENV AIW_HTTPS=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1

CMD ["python", "serve.py"]
