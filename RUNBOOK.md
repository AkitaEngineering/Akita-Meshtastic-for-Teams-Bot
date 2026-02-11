RUNBOOK: Akita Meshtastic for Teams Bot

Purpose
- Quick operational runbook for deploying, monitoring, and troubleshooting the bot in production.

Prerequisites
- Ensure secrets (TEAMS_APP_ID, TEAMS_APP_PASSWORD, MQTT_* etc.) are available from a secure store (Azure Key Vault, Kubernetes Secrets, or environment variables injected by platform).
- Ensure `MQTT_USE_TLS=True` in production and `MQTT_CA_CERTS` points to a CA bundle.

Quick health checks
- HTTP health endpoint:

```bash
curl http://<host>:<port>/health
```

- Prometheus metrics:

```bash
curl http://<host>:<port>/metrics
```

Common issues & troubleshooting
- MQTT not connected:
  - Verify `MQTT_BROKER_HOST`, `MQTT_BROKER_PORT`, and TLS settings.
  - Check MQTT broker logs and firewall connectivity.
  - Use `MQTT_TLS_INSECURE=False` in production; set true only for testing.

- Adaptive Card not rendering:
  - Ensure `bot/adaptive_cards/meshtastic_message.json` is valid JSON.

- Bot not responding in Teams:
  - Confirm `TEAMS_APP_ID` and `TEAMS_APP_PASSWORD` are correct and the messaging endpoint is registered in Azure Bot configuration.

Graceful shutdown
- The app honors system signals and will run `app.on_shutdown` handlers to disconnect MQTT.
- When deploying to Kubernetes, configure `terminationGracePeriodSeconds` >= 30 to allow clean disconnects.

Deploying via Docker (example)

```bash
# Build
docker build -t akita-meshtastic-bot:latest .

# Run (example)
docker run -e MQTT_BROKER_HOST=mybroker -e MQTT_USE_TLS=True -e MQTT_CA_CERTS=/certs/ca.pem -p 3978:3978 akita-meshtastic-bot:latest
```

Kubernetes example (simplified)
- See README.md for a sample Deployment manifest and service.

Contacts
- Akita Engineering: info@akitaengineering.com
