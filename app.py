import sys
import asyncio
import logging
from aiohttp import web
from botbuilder.core import TurnContext
from botbuilder.schema import Activity, ActivityTypes
from bot.config import SETTINGS
from bot.teams_adapter import ADAPTER # Use the global adapter instance
from bot.mqtt_client import MqttClientHandler
from bot.teams_bot import AkitaMeshtasticTeamsBot # Correct class name

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
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
     app.on_startup.append(start_background_tasks)
     app.on_shutdown.append(cleanup_background_tasks)
     app.router.add_post("/api/messages", messages)
     logger.info("AIOHTTP application configured for Akita Meshtastic for Teams Bot.")
     return app

# --- Main Execution ---
if __name__ == "__main__":
    try:
        # Use asyncio.run for simplicity if Python 3.7+
        app = asyncio.run(create_app())
        logger.info(f"Starting Akita Meshtastic for Teams Bot web server on port {SETTINGS.PORT}...")
        web.run_app(app, host="0.0.0.0", port=SETTINGS.PORT, loop=asyncio.get_event_loop())
    except KeyboardInterrupt:
        logger.info("Process interrupted by user.")
    except Exception as e:
         logger.exception(f"Fatal error during application startup or runtime: {e}")
         sys.exit(1)
    finally:
         logger.info("Application shutting down.")
