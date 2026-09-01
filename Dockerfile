# ═══════════════════════════════════════════════════════════════
# FENRIRBOT - Discord Bot
# Homelab monitoring and downtime announcements
# ═══════════════════════════════════════════════════════════════

FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY specs/ ./specs/
COPY run.py .

# Run as an unprivileged user. This process holds the Discord token and talks
# to socket-proxy, so it is the one container worth shrinking.
# NOTE: the host bind mount at ${DOCKERDIR}/appdata/fenrirbot/data must be
# chowned to 10001:10001 or the bot cannot persist scheduled maintenances.
RUN adduser -D -u 10001 fenrir \
    && mkdir -p /app/data \
    && chown -R fenrir:fenrir /app

USER fenrir

CMD ["python", "run.py"]
