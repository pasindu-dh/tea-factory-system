FROM python:3.12-slim

# The factory runs on Sri Lanka time; Render's default UTC would roll "today"
# over at 05:30 local, breaking attendance and payroll date rules.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Colombo \
    TEA_FACTORY_DB=/data/tea_factory.sqlite3

# setpriv (util-linux) lets the entrypoint fix the mounted disk's ownership as
# root and then drop to the unprivileged app user.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        tzdata util-linux \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persistent Render disks are mounted root-owned, so the entrypoint starts as
# root, chowns /data, then re-executes itself as `app`. CRLF is stripped in case
# the repository was checked out on Windows.
RUN mkdir -p /data \
    && chown -R app:app /app /data \
    && sed -i 's/\r$//' /app/docker-entrypoint.sh \
    && chmod +x /app/docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
