# Akita Meshtastic for Teams Bot

A Python-based bot to bridge communication between a Meshtastic mesh network (via MQTT) and Microsoft Teams. 
Developed by [Akita Engineering](https://www.akitaengineering.com).

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
## Features

* Relays messages received on the Meshtastic network (via MQTT) to a designated Teams channel/chat using Adaptive Cards.
* Allows sending messages from Teams back to the Meshtastic network (via MQTT).
* Provides node alias mapping for better readability of sender IDs.
* Ignores messages originating from the gateway node itself to prevent loops.
* Command to display bot configuration and current conversation ID.
* Uses Microsoft Bot Framework for Teams integration.
* Uses Paho-MQTT for MQTT communication.
* Configurable via environment variables.

## Prerequisites

* Python 3.8+
* An MQTT Broker accessible by the bot and your Meshtastic MQTT gateway node.
* A Meshtastic node configured with the MQTT module enabled (`uplink_enabled=true`, `downlink_enabled=true`).
* A Microsoft Teams account and a channel/chat for the bot.
* An Azure Bot registration (provides Microsoft App ID and Password).
* If using secure MQTT, a CA certificate or client cert/key as required by your MQTT broker.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/AkitaEngineering/Akita-Meshtastic-for-Teams-Bot.git
    cd Akita-Meshtastic-for-Teams-Bot
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**
    * Copy `.env.example` to `.env`.
    * Edit `.env` and fill in your specific details (MQTT broker, Azure Bot credentials, `MESH_GATEWAY_NODE_ID`, etc.). **Never commit your `.env` file!**
    ```bash
    cp .env.example .env
    nano .env # Or use your preferred editor
    ```
    * **Node Aliases:** You can define simple node aliases directly in `bot/config.py` within the `NODE_ALIASES` dictionary.

5.  **Run the bot:**
    ```bash
    python app.py
    ```
    * Ensure your bot's messaging endpoint (e.g., using ngrok for local testing or your deployed URL) is correctly configured in the Azure Bot registration.

## Configuration (`.env` file)

See `.env.example` for the list of required environment variables. Key variables include:

* `MQTT_BROKER_HOST`, `MQTT_BROKER_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`
* `MQTT_CLIENT_ID`
* `MQTT_BASE_TOPIC` (e.g., `msh/2/json`)
* TLS/SSL options for MQTT (if your broker requires TLS):
    * `MQTT_USE_TLS` - Set to `True` to enable TLS (connect to broker with TLS).
    * `MQTT_CA_CERTS` - Optional path to CA bundle to validate broker certificate.
    * `MQTT_CERTFILE` / `MQTT_KEYFILE` - Optional client certificate and key for mutual TLS.
    * `MQTT_TLS_INSECURE` - Optional; set to `True` to skip hostname verification (not recommended in production).
* `MESH_GATEWAY_NODE_ID` (**Required**, e.g., `!a1b2c3d4`)
* `TEAMS_APP_ID`, `TEAMS_APP_PASSWORD` (from Azure Bot registration)
* `TEAMS_TARGET_CONVERSATION_ID` (Optional: Use `@BotName bot info` command to find this ID)
* `PORT`

## Usage

* Once running and installed in Teams, Meshtastic messages forwarded via the configured MQTT topic should appear as Adaptive Cards in the designated Teams channel/chat.
* **Mention the bot** (e.g., `@AkitaMeshtasticBot`) followed by a command:
    * `mesh send <your message>` - Sends your message to the Meshtastic network.
    * `bot info` - Shows current bot configuration and the ID of the current Teams conversation (useful for setting `TEAMS_TARGET_CONVERSATION_ID`).
    * `help` or `mesh help` - Shows the help message.
    * `ping` - Checks if the bot is responsive.

    ## Health endpoint

    The application exposes a lightweight health endpoint useful for monitoring and TLS verification.

    Request:

    ```bash
    curl http://<host>:<port>/health
    ```

    Example response (JSON):

    ```json
    {
        "app": "ok",
        "mqtt": {
            "connected": true,
            "host": "mqtt.example.com",
            "port": 8883,
            "use_tls": true
        },
        "tls_check": {
            "ok": true,
            "message": "TLS handshake successful"
        }
    }
    ```

    If `use_tls` is true, the endpoint performs a quick TLS handshake against the configured MQTT broker using the `MQTT_CA_CERTS`, `MQTT_CERTFILE`, and `MQTT_KEYFILE` values where provided.

    ## Production checklist

    Minimum recommendations before production deploy:

    - Use a secret store (Azure Key Vault, Kubernetes Secrets) for `TEAMS_APP_ID`, `TEAMS_APP_PASSWORD`, and MQTT credentials. Avoid committing `.env`.
    - Set `ENVIRONMENT=production` and `MQTT_USE_TLS=True`. Provide `MQTT_CA_CERTS` and ensure `MQTT_TLS_INSECURE` is `False`.
    - Configure monitoring to scrape `/metrics` and alert on `mqtt_connected == 0` or repeated publish failures.
    - Run vulnerability scans on dependencies and container images as part of CI.

    See `RUNBOOK.md` for operational runbook and troubleshooting steps.

## OpenTelemetry (OTel) configuration

This project includes optional OpenTelemetry tracing. Traces can be exported to an OTLP-compatible collector (e.g., OpenTelemetry Collector, Grafana Agent, Tempo).

Environment variables:

- `OTEL_EXPORTER_OTLP_ENDPOINT`: OTLP HTTP endpoint (example: `http://otel-collector:4318/v1/traces`).
- `OTEL_EXPORTER_OTLP_INSECURE`: `true` to skip TLS when contacting the OTLP HTTP endpoint (useful for local testing).
- `OTEL_SERVICE_NAME`: Service name to appear in traces (default: `akita-meshtastic-bot`).
- `OTEL_AUTO_INSTRUMENT`: Set to `true` to enable automatic instrumentation for `aiohttp` (server) and `paho-mqtt`.

Quick examples:

Enable automatic instrumentation and point to a local collector:

```bash
export OTEL_AUTO_INSTRUMENT=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318/v1/traces
export OTEL_EXPORTER_OTLP_INSECURE=true
export OTEL_SERVICE_NAME=akita-meshtastic-bot
python app.py
```

If you prefer manual instrumentation (the default), the application adds a simple span for incoming HTTP requests and custom MQTT spans. Automatic instrumentation may create additional spans for aiohttp internals and MQTT operations.

Testing spans locally:

1. Run an OTLP-compatible collector locally (OpenTelemetry Collector or `otelcol`).
2. Set `OTEL_EXPORTER_OTLP_ENDPOINT` to the collector endpoint and start the app.
3. Exercise endpoints (e.g., `curl http://localhost:3978/health` and send a bot message) and inspect the collector's output or backend.


## Contributing

Contributions are welcome! Please open an issue or submit a pull request. Contact <info@akitaengineering.com> for inquiries.

## License

Copyright (C) 2025 Akita Engineering

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
