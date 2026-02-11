import os
import json
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

# --- Node Alias Configuration ---
# Simple in-memory dictionary for node aliases.
# In a more complex setup, you might load this from a file or database.
# Keys should be the full node ID string (e.g., "!abcdef12")
NODE_ALIASES = {
    # Example entries - Replace with your actual node IDs and desired names
    # "!abcdef12": "Base Station",
    # "!12345678": "Rooftop Repeater",
}
# Optional: Load aliases from a JSON file if it exists
# ALIAS_FILE_PATH = os.getenv("NODE_ALIAS_FILE_PATH", "node_aliases.json")
# try:
#     if os.path.exists(ALIAS_FILE_PATH):
#         with open(ALIAS_FILE_PATH, 'r') as f:
#             NODE_ALIASES.update(json.load(f))
#         logger.info(f"Loaded node aliases from {ALIAS_FILE_PATH}")
# except Exception as e:
#     logger.warning(f"Could not load node aliases from {ALIAS_FILE_PATH}: {e}")


class Settings:
    # --- MQTT Configuration ---
    MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST")
    MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", 1883))
    MQTT_USERNAME = os.getenv("MQTT_USERNAME") # Can be None
    MQTT_PASSWORD = os.getenv("MQTT_PASSWORD") # Can be None
    MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "AkitaMeshtasticTeamsBot-Default")
    MQTT_BASE_TOPIC = os.getenv("MQTT_BASE_TOPIC", "msh/2/json").rstrip('/')
    MQTT_USE_TLS = os.getenv("MQTT_USE_TLS", "False").lower() == "true"
    MQTT_PRIMARY_CHANNEL_NAME = os.getenv("MQTT_PRIMARY_CHANNEL_NAME", "LongFast")
    # Optional TLS/SSL certificate paths for MQTT
    MQTT_CA_CERTS = os.getenv("MQTT_CA_CERTS")  # Path to CA bundle file
    MQTT_CERTFILE = os.getenv("MQTT_CERTFILE")  # Client cert (optional)
    MQTT_KEYFILE = os.getenv("MQTT_KEYFILE")    # Client key (optional)
    MQTT_TLS_INSECURE = os.getenv("MQTT_TLS_INSECURE", "False").lower() == "true"

    # --- Microsoft Teams Bot Configuration ---
    TEAMS_APP_ID = os.getenv("TEAMS_APP_ID")
    TEAMS_APP_PASSWORD = os.getenv("TEAMS_APP_PASSWORD")

    # --- Bot Operation ---
    MESH_GATEWAY_NODE_ID = os.getenv("MESH_GATEWAY_NODE_ID") # e.g., !a1b2c3d4
    TEAMS_TARGET_CONVERSATION_ID = os.getenv("TEAMS_TARGET_CONVERSATION_ID")

    # Web Server Port
    PORT = int(os.getenv("PORT", 3978))

    # --- Node Aliases ---
    # Make aliases accessible via settings instance
    NODE_ALIASES = NODE_ALIASES

    def validate(self) -> bool:
        """Validate that essential configuration is set."""
        required = [
            self.MQTT_BROKER_HOST,
            self.MQTT_BASE_TOPIC,
            self.TEAMS_APP_ID,
            self.TEAMS_APP_PASSWORD,
            self.MESH_GATEWAY_NODE_ID # Required for sending
        ]
        if not all(required):
            logger.error("Missing one or more required environment variables: "
                         "MQTT_BROKER_HOST, MQTT_BASE_TOPIC, TEAMS_APP_ID, "
                         "TEAMS_APP_PASSWORD, MESH_GATEWAY_NODE_ID")
            return False
        if not self.MESH_GATEWAY_NODE_ID or not self.MESH_GATEWAY_NODE_ID.startswith('!'):
             logger.error("MESH_GATEWAY_NODE_ID must be set and start with '!'")
             return False

        if self.MQTT_USE_TLS and self.MQTT_BROKER_PORT == 1883:
            logger.warning("MQTT_USE_TLS is True, but MQTT_BROKER_PORT is 1883 (standard non-TLS port). Consider using port 8883.")
        if not self.MQTT_USE_TLS and self.MQTT_BROKER_PORT == 8883:
            logger.warning("MQTT_USE_TLS is False, but MQTT_BROKER_PORT is 8883 (standard TLS port).")

        # Warn if TLS is enabled but no CA bundle provided (system CA may still be used)
        if self.MQTT_USE_TLS and not self.MQTT_CA_CERTS:
            logger.info("MQTT_USE_TLS is enabled but MQTT_CA_CERTS is not set. System CA bundle will be used if available.")

        # Enforce TLS in production environment
        if os.getenv("ENVIRONMENT", "dev").lower() == "production":
            if not self.MQTT_USE_TLS:
                logger.error("Running in production requires MQTT_USE_TLS=True. Set MQTT_USE_TLS and provide MQTT_CA_CERTS.")
                return False
            if self.MQTT_TLS_INSECURE:
                logger.error("Running in production with MQTT_TLS_INSECURE=True is not allowed. Disable insecure TLS verification.")
                return False

        logger.info("Configuration validated successfully.")
        return True

    def _load_from_azure_keyvault(self) -> None:
        """Optional: load secrets from Azure Key Vault if AZURE_KEYVAULT_URL is set.

        This attempts to import Azure SDK packages and retrieve secrets that
        match the environment variable names used by this app. If Azure SDK is
        not installed or authentication is not configured, this will log and
        continue using environment variables.
        """
        kv_url = os.getenv("AZURE_KEYVAULT_URL")
        if not kv_url:
            return

        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient
        except Exception as e:
            logger.warning(f"Azure Key Vault packages not available: {e}")
            return

        try:
            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=kv_url, credential=credential)
            # List of secret keys to attempt to fetch; override if found
            keys = [
                "MQTT_BROKER_HOST",
                "MQTT_BROKER_PORT",
                "MQTT_USERNAME",
                "MQTT_PASSWORD",
                "TEAMS_APP_ID",
                "TEAMS_APP_PASSWORD",
                "MESH_GATEWAY_NODE_ID",
            ]
            for key in keys:
                try:
                    secret = client.get_secret(key)
                    if secret and secret.value is not None:
                        # set on instance
                        # convert port to int where appropriate
                        if key == "MQTT_BROKER_PORT":
                            try:
                                setattr(self, key, int(secret.value))
                            except Exception:
                                setattr(self, key, secret.value)
                        else:
                            setattr(self, key, secret.value)
                        logger.info(f"Loaded secret for {key} from Azure Key Vault")
                except Exception:
                    # ignore missing secret
                    pass
        except Exception as e:
            logger.warning(f"Could not read secrets from Azure Key Vault: {e}")


# Create a single instance of settings to be imported
SETTINGS = Settings()
# Attempt to load secrets from Azure Key Vault if configured (best-effort)
try:
    SETTINGS._load_from_azure_keyvault()
except Exception:
    # Avoid failing import if Key Vault access fails; we already log issues inside
    pass
