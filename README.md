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

## Setup

1.  **Clone the repository:**
    ```bash
    # Replace with Akita Engineering's repo URL when created
    git clone [https://github.com/akita-engineering/meshtastic-teams-bot.git](https://github.com/akita-engineering/meshtastic-teams-bot.git)
    cd meshtastic-teams-bot
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

## Contributing

Contributions are welcome! Please open an issue or submit a pull request. Contact <info@akitaengineering.com> for inquiries.

## License

Copyright (C) 2025 Akita Engineering

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
