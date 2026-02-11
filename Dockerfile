FROM python:3.11-slim AS builder

WORKDIR /src
COPY requirements.txt ./
RUN apt-get update \
	&& apt-get install -y --no-install-recommends build-essential libssl-dev libffi-dev python3-dev \
	&& python -m venv /opt/venv \
	&& /opt/venv/bin/pip install --upgrade pip setuptools wheel \
	&& /opt/venv/bin/pip install --no-cache-dir -r requirements.txt \
	&& rm -rf /var/lib/apt/lists/* /root/.cache

FROM python:3.11-slim

ARG USER=app
ARG UID=1000

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1

# Copy only application files
COPY . /app

# Install runtime CA certs
RUN apt-get update \
	&& apt-get install -y --no-install-recommends ca-certificates \
	&& rm -rf /var/lib/apt/lists/* \
	&& groupadd -g ${UID} ${USER} || true \
	&& useradd -m -u ${UID} -g ${UID} -s /usr/sbin/nologin ${USER} || true \
	&& chown -R ${USER}:${USER} /app

EXPOSE 3978

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 CMD python -c "import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:3978/health'); sys.exit(0 if r.getcode()==200 else 1)"

USER ${USER}

CMD ["python", "app.py"]
