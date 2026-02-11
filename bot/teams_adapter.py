import logging
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings
from botbuilder.schema import ConversationReference
from bot.config import SETTINGS

logger = logging.getLogger(__name__)

# Create the adapter with app credentials
ADAPTER_SETTINGS = BotFrameworkAdapterSettings(
    app_id=SETTINGS.TEAMS_APP_ID,
    app_password=SETTINGS.TEAMS_APP_PASSWORD
)
ADAPTER = BotFrameworkAdapter(ADAPTER_SETTINGS)

# Global storage for conversation references (for proactive messaging)
_conversation_references = {}

def add_conversation_reference(activity):
    """Store a conversation reference for later proactive messaging."""
    if activity and activity.conversation:
        conv_id = activity.conversation.id
        ref = ConversationReference.from_activity(activity)
        _conversation_references[conv_id] = ref
        logger.debug(f"Stored conversation reference for ID: {conv_id}")

def get_default_conversation_reference():
    """Get the default conversation reference (first stored one or from env)."""
    # If TEAMS_TARGET_CONVERSATION_ID is set, use that
    if SETTINGS.TEAMS_TARGET_CONVERSATION_ID and SETTINGS.TEAMS_TARGET_CONVERSATION_ID in _conversation_references:
        return _conversation_references[SETTINGS.TEAMS_TARGET_CONVERSATION_ID]
    # Otherwise, return the first one stored
    if _conversation_references:
        return next(iter(_conversation_references.values()))
    return None