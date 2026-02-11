import json
import logging
import time
import paho.mqtt.client as mqtt
from bot.config import SETTINGS
from opentelemetry import trace

from prometheus_client import Counter, Gauge

logger = logging.getLogger(__name__)

# Prometheus metrics
MQTT_CONNECTS = Counter("mqtt_connects_total", "Total MQTT connect attempts")
MQTT_DISCONNECTS = Counter("mqtt_disconnects_total", "Total MQTT disconnects")
MQTT_PUBLISH_SUCCESS = Counter("mqtt_publish_success_total", "Successful MQTT publishes")
MQTT_PUBLISH_FAILURE = Counter("mqtt_publish_failure_total", "Failed MQTT publishes")
MQTT_CONNECTED_GAUGE = Gauge("mqtt_connected", "MQTT connected (1=true,0=false)")


class MqttClientHandler:
    def __init__(self):
        # Use persistent session where available
        try:
            self.client = mqtt.Client(client_id=SETTINGS.MQTT_CLIENT_ID, clean_session=False)
        except TypeError:
            # Older paho versions may not support clean_session arg
            self.client = mqtt.Client(client_id=SETTINGS.MQTT_CLIENT_ID)

        # Optional username/password
        if SETTINGS.MQTT_USERNAME or SETTINGS.MQTT_PASSWORD:
            self.client.username_pw_set(SETTINGS.MQTT_USERNAME, SETTINGS.MQTT_PASSWORD)

        # Configure automatic reconnect backoff
        try:
            # Use reasonable defaults for reconnect delays (min 1s, max 120s)
            self.client.reconnect_delay_set(min_delay=1, max_delay=120)
        except Exception:
            # Older paho versions may not have this method; ignore if not present
            pass

        # TLS/SSL configuration if enabled
        if SETTINGS.MQTT_USE_TLS:
            try:
                # Use provided CA certs / client cert / key if available, otherwise default system CAs
                ca = SETTINGS.MQTT_CA_CERTS or None
                certfile = SETTINGS.MQTT_CERTFILE or None
                keyfile = SETTINGS.MQTT_KEYFILE or None
                self.client.tls_set(ca_certs=ca, certfile=certfile, keyfile=keyfile)
                # Allow skipping cert verification if requested (useful for testing)
                if SETTINGS.MQTT_TLS_INSECURE:
                    # paho uses tls_insecure_set to disable hostname verification
                    self.client.tls_insecure_set(True)
                logger.debug("Configured MQTT TLS/SSL settings")
            except Exception as e:
                logger.exception(f"Failed to configure MQTT TLS: {e}")

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish = self._on_publish
        self._on_meshtastic_message_callback = None  # Callback for incoming messages
        self.connected = False

    def connect(self):
        """Connect to the MQTT broker and start the loop."""
        try:
            # Start network loop before attempting connection
            self.client.loop_start()

            # Attempt connection with exponential backoff if initial connect fails
            attempt = 0
            max_attempts = 5
            backoff = 1
            while attempt < max_attempts:
                try:
                    self.client.connect(SETTINGS.MQTT_BROKER_HOST, SETTINGS.MQTT_BROKER_PORT, 60)
                    logger.info(f"Connecting to MQTT broker at {SETTINGS.MQTT_BROKER_HOST}:{SETTINGS.MQTT_BROKER_PORT}")
                    break
                except Exception as e:
                    attempt += 1
                    logger.warning(f"MQTT connect attempt {attempt} failed: {e}. Retrying in {backoff}s")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 30)
            else:
                logger.error("Exceeded maximum MQTT connect attempts")
                raise
        except Exception as e:
            logger.exception(f"Failed to connect to MQTT broker: {e}")
            raise

    def disconnect(self):
        """Disconnect from the MQTT broker."""
        if self.connected:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
            logger.info("Disconnected from MQTT broker")

    def publish_to_meshtastic_channel(self, message: str) -> bool:
        """Publish a message to the Meshtastic MQTT channel."""
        if not self.connected:
            logger.error("Cannot publish: MQTT client not connected")
            return False
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("mqtt.publish"):
            try:
                import base64
                # Construct the payload for Meshtastic
                payload = {
                    "type": "text",
                    "payload": base64.b64encode(message.encode('utf-8')).decode('ascii'),  # Base64 encoded
                    "to": 0,  # Broadcast
                    # Strip leading '!' if present before hex->int conversion
                    "from": int(SETTINGS.MESH_GATEWAY_NODE_ID.lstrip('!'), 16) if isinstance(SETTINGS.MESH_GATEWAY_NODE_ID, str) and SETTINGS.MESH_GATEWAY_NODE_ID.startswith('!') else 0,
                    "channel": SETTINGS.MQTT_PRIMARY_CHANNEL_NAME
                }
                topic = f"{SETTINGS.MQTT_BASE_TOPIC}/{SETTINGS.MQTT_PRIMARY_CHANNEL_NAME}/in"
                # Attempt publish with retries and wait for confirmation
                max_attempts = 3
                for attempt in range(1, max_attempts + 1):
                    result = self.client.publish(topic, json.dumps(payload), qos=1)
                    try:
                        # Wait for the message to be sent/acknowledged
                        result.wait_for_publish(timeout=5)
                    except Exception:
                        pass

                    # Consider publish successful if either rc indicates success or is_published is True
                    rc = getattr(result, "rc", None)
                    if rc == mqtt.MQTT_ERR_SUCCESS or getattr(result, "is_published", lambda: False)():
                        logger.info(f"Published message to MQTT topic: {topic}")
                        MQTT_PUBLISH_SUCCESS.inc()
                        return True

                    logger.warning(f"Publish attempt {attempt} failed (rc={rc}).")
                    MQTT_PUBLISH_FAILURE.inc()
                    time.sleep(attempt)

                logger.error("Failed to publish message after retries")
                return False
            except Exception as e:
                logger.exception(f"Error publishing message: {e}")
                return False

    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected to MQTT broker."""
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("mqtt.connect"):
            if rc == 0:
                self.connected = True
                logger.info("Connected to MQTT broker")
                MQTT_CONNECTS.inc()
                MQTT_CONNECTED_GAUGE.set(1)
                # Subscribe to the topic for incoming messages
                topic = f"{SETTINGS.MQTT_BASE_TOPIC}/#"
                self.client.subscribe(topic, qos=1)
                logger.info(f"Subscribed to MQTT topic: {topic}")
            else:
                logger.error(f"Failed to connect to MQTT broker: {rc}")

    def _on_message(self, client, userdata, msg):
        """Callback when a message is received."""
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("mqtt.on_message"):
            try:
                payload = json.loads(msg.payload.decode('utf-8'))
                logger.debug(f"Received MQTT message on topic: {msg.topic}")
                if self._on_meshtastic_message_callback:
                    self._on_meshtastic_message_callback(msg.topic, payload)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to decode MQTT message as JSON: {e}")
            except Exception as e:
                logger.exception(f"Error processing MQTT message: {e}")

    def _on_disconnect(self, client, userdata, rc):
        """Callback when disconnected from MQTT broker."""
        self.connected = False
        MQTT_DISCONNECTS.inc()
        MQTT_CONNECTED_GAUGE.set(0)
        if rc != 0:
            logger.warning(f"Unexpected disconnection from MQTT broker: {rc}")
        else:
            logger.info("Disconnected from MQTT broker")

    def _on_publish(self, client, userdata, mid):
        """Callback when a message is published."""
        logger.debug(f"Message published (mid={mid})")
        MQTT_PUBLISH_SUCCESS.inc()