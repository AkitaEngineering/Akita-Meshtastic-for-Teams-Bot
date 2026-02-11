import sys
import asyncio
import logging
from pythonjsonlogger import jsonlogger
import ssl
import socket
from typing import Tuple
from aiohttp import web
from botbuilder.core import TurnContext
from botbuilder.schema import Activity, ActivityTypes
from bot.config import SETTINGS
from bot.teams_adapter import ADAPTER # Use the global adapter instance
from bot.mqtt_client import MqttClientHandler
from bot.teams_bot import AkitaMeshtasticTeamsBot # Correct class name
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

# --- Logging Setup (structured JSON) ---
handler = logging.StreamHandler(stream=sys.stdout)
formatter = jsonlogger.JsonFormatter('%(asctime)s %(name)s %(levelname)s %(message)s')
handler.setFormatter(formatter)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(handler)
# Reduce noise from third-party libraries
logging.getLogger("botbuilder").setLevel(logging.INFO)
logging.getLogger("paho").setLevel(logging.INFO)
# Set specific logger level for noisy modules if needed
# logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- Global Variables ---
MQTT_CLIENT: MqttClientHandler = None
BOT: AkitaMeshtasticTeamsBot = None

# --- Web Server Request Handler ---
async def messages(req: web.Request) -> web.Response:
    """Main endpoint for receiving messages from Bot Framework Service."""
    if "application/json" not in req.headers.get("Content-Type", ""):
        logger.warning("Received request with unsupported Content-Type.")
        return web.Response(status=415) # Unsupported Media Type

    body = await req.json()
    activity = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")

    # Log basic activity info (avoid logging full body unless debugging sensitive data)
    logger.info(f"Received activity. Type: {activity.type}. Conv: {activity.conversation.id}. From: {activity.from_property.id if activity.from_property else 'N/A'}.")

    try:
        if not BOT:
             logger.error("Bot object is not initialized. Cannot process activity.")
             return web.Response(status=503) # Service Unavailable

        response = await ADAPTER.process_activity(activity, auth_header, BOT.on_turn)
        if response:
            logger.debug(f"Sending response status: {response.status}")
            return web.json_response(response.body, status=response.status)
        logger.debug("Activity processed, no response body generated (status 201).")
        return web.Response(status=201) # Accepted
    except Exception as error:
        logger.exception(f"Error processing activity: {error}")
        return web.Response(status=500)


def _check_tls_handshake(host: str, port: int, cafile: str = None, certfile: str = None, keyfile: str = None, insecure: bool = False, timeout: int = 5) -> Tuple[bool, str]:
    """Perform a short TLS handshake against the broker to validate certs.

    Returns (success, message). This is a synchronous helper intended to be
    run in a thread via `asyncio.to_thread` from async code.
    """
    try:
        if insecure:
            context = ssl._create_unverified_context()
        else:
            context = ssl.create_default_context()
        if cafile:
            # load_verify_locations accepts None to use defaults
            context.load_verify_locations(cafile)
        if certfile:
            context.load_cert_chain(certfile, keyfile)

        with socket.create_connection((host, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host if not insecure else None) as ssock:
                # If handshake completes without exception, success
                peercert = ssock.getpeercert()
                return True, "TLS handshake successful"
    except Exception as e:
        return False, str(e)


async def health(req: web.Request) -> web.Response:
    """Health endpoint. Reports app status, MQTT connection state, and TLS handshake result if applicable."""
    mqtt_connected = False
    tls_check = None
    if MQTT_CLIENT:
        try:
            mqtt_connected = bool(MQTT_CLIENT.connected)
        except Exception:
            mqtt_connected = False

    if SETTINGS.MQTT_USE_TLS:
        # Run TLS check in a thread to avoid blocking the event loop
        success, message = await asyncio.to_thread(
            _check_tls_handshake,
            SETTINGS.MQTT_BROKER_HOST,
            SETTINGS.MQTT_BROKER_PORT,
            SETTINGS.MQTT_CA_CERTS,
            SETTINGS.MQTT_CERTFILE,
            SETTINGS.MQTT_KEYFILE,
            SETTINGS.MQTT_TLS_INSECURE,
            5,
        )
        tls_check = {"ok": success, "message": message}

    payload = {
        "app": "ok",
        "mqtt": {"connected": mqtt_connected, "host": SETTINGS.MQTT_BROKER_HOST, "port": SETTINGS.MQTT_BROKER_PORT, "use_tls": SETTINGS.MQTT_USE_TLS},
        "tls_check": tls_check,
    }
    return web.json_response(payload)


async def metrics(req: web.Request) -> web.Response:
    """Prometheus metrics endpoint."""
    data = generate_latest()
    return web.Response(body=data, content_type=CONTENT_TYPE_LATEST)

# --- Application Setup ---
async def start_background_tasks(app):
    """Connect MQTT client and initialize Bot when app starts."""
    global MQTT_CLIENT, BOT
    logger.info("Starting background tasks (MQTT connection and Bot init)...")
    try:
        MQTT_CLIENT = MqttClientHandler()
        BOT = AkitaMeshtasticTeamsBot(mqtt_client=MQTT_CLIENT) # Pass client to bot
        logger.info("Akita Meshtastic for Teams Bot initialized successfully.")
        MQTT_CLIENT.connect() # Start connection and loop
        app["mqtt_client"] = MQTT_CLIENT
        app["bot"] = BOT
    except Exception as e:
         logger.exception(f"Critical error during background task startup: {e}")
         raise # Stop app startup if essential components fail

async def cleanup_background_tasks(app):
    """Disconnect MQTT client when app stops."""
    logger.info("Cleaning up background tasks (MQTT disconnect)...")
    if app.get("mqtt_client"):
        app["mqtt_client"].disconnect()
    logger.info("Cleanup complete.")

async def create_app() -> web.Application:
    """Creates the AIOHTTP web application."""
    if not SETTINGS.validate():
        logger.critical("Configuration validation failed. Please check your .env file. Exiting.")
        sys.exit(1)

    app = web.Application()
    # OpenTelemetry tracing setup
    otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or os.getenv("OTEL_OTLP_ENDPOINT")
    resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "akita-meshtastic-bot")})
    tracer_provider = TracerProvider(resource=resource)
    if otel_endpoint:
        exporter = OTLPSpanExporter(endpoint=otel_endpoint, insecure=True if os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() in ("1", "true") else False)
        tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(tracer_provider)

    # Automatic instrumentation (optional)
    if os.getenv("OTEL_AUTO_INSTRUMENT", "false").lower() in ("1", "true"):
        try:
            from opentelemetry.instrumentation.aiohttp_server import AioHttpServerInstrumentor

            AioHttpServerInstrumentor().instrument()
            logger.info("OpenTelemetry auto-instrumentation enabled for aiohttp (paho-mqtt instrumented manually)")
        except Exception as e:
            logger.warning(f"Auto-instrumentation failed: {e}")
    else:
        # Fallback: create spans for HTTP requests via simple middleware
        @web.middleware
        async def otel_middleware(request, handler):
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span(f"http {request.method} {request.path}"):
                return await handler(request)

        app.middlewares.append(otel_middleware)
    app.on_startup.append(start_background_tasks)
    app.on_shutdown.append(cleanup_background_tasks)
    app.router.add_get("/health", health)
    app.router.add_get("/metrics", metrics)
    app.router.add_post("/api/messages", messages)
    logger.info("AIOHTTP application configured for Akita Meshtastic for Teams Bot.")
    return app

# --- Main Execution ---
if __name__ == "__main__":
    try:
        # Use asyncio.run for simplicity if Python 3.7+
        app = asyncio.run(create_app())
        logger.info(f"Starting Akita Meshtastic for Teams Bot web server on port {SETTINGS.PORT}...")
        # web.run_app will handle signals and call app.on_shutdown handlers.
        # Use a reasonable shutdown timeout.
        web.run_app(app, host="0.0.0.0", port=SETTINGS.PORT, shutdown_timeout=10)
    except KeyboardInterrupt:
        logger.info("Process interrupted by user.")
    except Exception as e:
         logger.exception(f"Fatal error during application startup or runtime: {e}")
         sys.exit(1)
    finally:
         logger.info("Application shutting down.")
