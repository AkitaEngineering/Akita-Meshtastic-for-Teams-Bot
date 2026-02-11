import logging
import asyncio
import json
import copy # For deep copying the card template
from pathlib import Path
from botbuilder.core import ActivityHandler, TurnContext, MessageFactory, CardFactory
from botbuilder.schema import ChannelAccount, Activity, ActivityTypes, ConversationReference, Attachment

from bot.config import SETTINGS # Import the single settings instance
from bot.mqtt_client import MqttClientHandler
# Import ADAPTER using its definition file
from bot.teams_adapter import ADAPTER, add_conversation_reference, get_default_conversation_reference

logger = logging.getLogger(__name__)

class AkitaMeshtasticTeamsBot(ActivityHandler):
    def __init__(self, mqtt_client: MqttClientHandler):
        self.mqtt_client = mqtt_client
        # Assign the bot's method as the callback for the MQTT client
        self.mqtt_client._on_meshtastic_message_callback = self.handle_incoming_meshtastic_message
        logger.info("Akita Meshtastic for Teams Bot initialized.")

        # Load Adaptive Card template
        self.meshtastic_message_card = None # Initialize as None
        try:
            # Construct path relative to this file
            card_path = Path(__file__).resolve().parent / "adaptive_cards" / "meshtastic_message.json"
            if card_path.is_file():
                with open(card_path, "r") as f:
                    self.meshtastic_message_card = json.load(f)
                logger.info("Successfully loaded Adaptive Card template.")
            else:
                logger.warning(f"Adaptive Card template file not found at: {card_path}")
        except Exception as e:
            logger.exception(f"Error loading Adaptive Card template: {e}")
            self.meshtastic_message_card = None # Ensure it's None if loading failed

    async def on_turn(self, turn_context: TurnContext):
        """Overrides default on_turn to store conversation reference."""
        await super().on_turn(turn_context)
        # Store conversation reference for potential proactive messages later
        if turn_context.activity.type == ActivityTypes.message and turn_context.activity.from_property.id != turn_context.activity.recipient.id:
             add_conversation_reference(turn_context.activity)
             logger.debug(f"Stored/Updated conv ref for ID: {turn_context.activity.conversation.id}")

    async def on_message_activity(self, turn_context: TurnContext):
        """Handles incoming messages from Teams."""
        text = turn_context.activity.text.strip() if turn_context.activity.text else ""
        cleaned_text = TurnContext.remove_recipient_mention(turn_context.activity) or text
        cleaned_text = cleaned_text.strip()

        logger.info(f"Received Teams message: '{text}' (Cleaned: '{cleaned_text}') from User: {turn_context.activity.from_property.name}")

        parts = cleaned_text.lower().split(maxsplit=2)
        command = parts[0] if parts else ""

        if command == "mesh":
            if len(parts) > 1:
                sub_command = parts[1]
                if sub_command == "send":
                    if len(parts) > 2:
                        message_to_send = cleaned_text.split(maxsplit=2)[2]
                        logger.info(f"Attempting to send to Meshtastic: '{message_to_send}'")
                        success = self.mqtt_client.publish_to_meshtastic_channel(message_to_send)
                        if success:
                            await turn_context.send_activity(MessageFactory.text("✅ Message sent to Meshtastic network via MQTT."))
                        else:
                            await turn_context.send_activity(MessageFactory.text("❌ Failed to send message via MQTT. Check logs and MQTT connection."))
                    else:
                        await turn_context.send_activity(MessageFactory.text("Usage: `@BotName mesh send <your message>`"))
                elif sub_command == "help":
                    await self._send_help_message(turn_context)
                else:
                     await turn_context.send_activity(MessageFactory.text(f"Unknown 'mesh' command: '{sub_command}'. Try `@BotName mesh help`."))
            else:
                 await self._send_help_message(turn_context)

        # NEW COMMAND: bot info
        elif command == "bot" and len(parts) > 1 and parts[1] == "info":
            conv_id = turn_context.activity.conversation.id
            reply_text = (
                f"**Akita Meshtastic Bot Info**\n\n"
                f"* **Conversation ID:** `{conv_id}`\n"
                f"* **MQTT Broker:** `{SETTINGS.MQTT_BROKER_HOST}:{SETTINGS.MQTT_BROKER_PORT}`\n"
                f"* **MQTT Base Topic:** `{SETTINGS.MQTT_BASE_TOPIC}`\n"
                f"* **Mesh Gateway Node ID:** `{SETTINGS.MESH_GATEWAY_NODE_ID}`\n"
                f"* **Target Conv ID (from .env):** `{SETTINGS.TEAMS_TARGET_CONVERSATION_ID or 'Not Set'}`\n"
                f"* **Node Aliases Loaded:** {len(SETTINGS.NODE_ALIASES)} entries"
            )
            await turn_context.send_activity(MessageFactory.text(reply_text))

        elif command == "help":
             await self._send_help_message(turn_context)
        elif command == "ping":
             await turn_context.send_activity(MessageFactory.text("Pong! Akita Meshtastic for Teams is connected."))
        # Default response if mentioned but command not recognized
        # elif TurnContext.get_mention_entities(turn_context.activity): # Check if bot was mentioned
        #      await turn_context.send_activity(MessageFactory.text(f"Hello! I'm Akita Meshtastic for Teams. Try `@BotName mesh help` or `@BotName bot info`."))


    async def _send_help_message(self, turn_context: TurnContext):
        """Sends help instructions to Teams."""
        # UPDATED Help Text
        help_text = (
            "**Akita Meshtastic for Teams Bot Help**\n\n"
            "Replace `@BotName` below with the actual name you use to mention me.\n\n"
            "Commands:\n"
            "* `@BotName mesh send <your message>` - Sends your message to the Meshtastic network's primary channel.\n"
            "* `@BotName bot info` - Shows current bot configuration and conversation ID.\n"
            "* `@BotName mesh help` / `@BotName help` - Shows this help message.\n"
            "* `@BotName ping` - Check if the bot is responsive."
        )
        await turn_context.send_activity(MessageFactory.text(help_text))

    async def on_members_added_activity(
        self, members_added: [ChannelAccount], turn_context: TurnContext
    ):
        """Greets new members added to the conversation (including the bot itself)."""
        bot_name = turn_context.activity.recipient.name or "Akita Meshtastic for Teams"
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                logger.info(f"Member added: {member.name} (ID: {member.id})")
                await turn_context.send_activity(
                    f"Welcome {member.name}! I'm {bot_name}. I relay messages between this chat and the Meshtastic network. Try `@BotName mesh help`."
                )
            else:
                 logger.info(f"{bot_name} added to conversation.")
                 await turn_context.send_activity(f"{bot_name} reporting for duty! Mention me and use `mesh help` or `bot info`.")
                 logger.info(f"Bot added to Conversation ID: {turn_context.activity.conversation.id}. "
                             f"Set this as TEAMS_TARGET_CONVERSATION_ID in .env if you want proactive messages here.")
                 add_conversation_reference(turn_context.activity)

    async def handle_incoming_meshtastic_message(self, topic: str, payload: dict):
        """Processes messages received from MQTT and sends them to Teams."""
        logger.info(f"Handling incoming Meshtastic message from topic: {topic}")
        try:
            # --- Extract sender ID ---
            sender_id_int = payload.get("from")
            sender_id_str = payload.get("fromId")
            sender_id = sender_id_str or (f"!{sender_id_int:x}" if isinstance(sender_id_int, int) else "Unknown")

            # --- Ignore messages from own gateway ---
            if sender_id == SETTINGS.MESH_GATEWAY_NODE_ID:
                logger.debug(f"Ignoring message from own gateway node ID: {sender_id}")
                return

            # --- Extract message text ---
            message_text = None
            decoded_payload = payload.get('decoded', {})
            packet_payload = payload.get('payload', {})

            if isinstance(decoded_payload, dict) and 'text' in decoded_payload:
                message_text = decoded_payload.get('text')
            elif isinstance(packet_payload, dict) and 'text' in packet_payload:
                 message_text = packet_payload.get('text')
            elif isinstance(packet_payload, str) and payload.get("type") == "text":
                try:
                    import base64
                    message_text = base64.b64decode(packet_payload).decode('utf-8')
                except Exception:
                    logger.warning(f"Could not decode base64 payload for supposed text message: {packet_payload[:30]}...")
                    message_text = "[Non-text payload]"

            if message_text is None:
                packet_type = decoded_payload.get("portnum") or payload.get("type", "unknown")
                logger.debug(f"Ignoring non-text Meshtastic payload (Type: {packet_type}) from {sender_id}")
                return

            # --- Get Node Alias ---
            display_name = SETTINGS.NODE_ALIASES.get(sender_id, sender_id) # Use alias if found, else use ID

            # --- Send proactively to Teams ---
            conv_ref = get_default_conversation_reference()
            if not conv_ref:
                logger.warning("Cannot send Meshtastic message to Teams: No target conversation reference available/configured.")
                return

            # --- Prepare and Send Message/Card ---
            if self.meshtastic_message_card:
                # Use Adaptive Card
                card_data = {
                    "sender": display_name,
                    "message": message_text,
                    "topic": topic # Include topic for context
                }
                # Create a deep copy to avoid modifying the template
                card_payload = copy.deepcopy(self.meshtastic_message_card)

                # Simple substitution (more robust templating engines exist)
                # This assumes ${variable} syntax in the card JSON
                card_json_str = json.dumps(card_payload)
                for key, value in card_data.items():
                    # Basic escaping for JSON strings
                    escaped_value = json.dumps(str(value))[1:-1]
                    card_json_str = card_json_str.replace(f"${{{key}}}", escaped_value)

                try:
                    final_card = json.loads(card_json_str)
                    attachment = CardFactory.adaptive_card(final_card)
                    activity_to_send = MessageFactory.attachment(attachment)
                    logger.info(f"Sending Adaptive Card to Teams conversation: {conv_ref.conversation.id}")
                except json.JSONDecodeError as json_err:
                     logger.error(f"Failed to decode JSON after substitution for Adaptive Card: {json_err}")
                     # Fallback to text message on card error
                     fallback_text = f"📡 **Akita Meshtastic [{display_name}]**: {message_text}\n_(Error displaying card)_"
                     activity_to_send = MessageFactory.text(fallback_text)
                     logger.info(f"Sending fallback text message to Teams conversation: {conv_ref.conversation.id}")

            else:
                # Fallback to plain text if card template failed to load
                teams_message = f"📡 **Akita Meshtastic [{display_name}]**: {message_text}"
                activity_to_send = MessageFactory.text(teams_message)
                logger.info(f"Sending plain text message to Teams conversation: {conv_ref.conversation.id}")


            async def _send_activity_async(turn_context: TurnContext):
                await turn_context.send_activity(activity_to_send)

            await ADAPTER.continue_conversation(
                conv_ref,
                _send_activity_async,
                SETTINGS.TEAMS_APP_ID
            )

        except Exception as e:
            logger.exception(f"Error processing incoming Meshtastic message: {e}")

