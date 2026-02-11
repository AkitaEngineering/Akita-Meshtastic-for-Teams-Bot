import json
import pytest

from bot.mqtt_client import MqttClientHandler


class DummyPubResult:
    def __init__(self, rc):
        self.rc = rc


def test_publish_not_connected(monkeypatch):
    mc = MqttClientHandler()
    mc.connected = False
    assert mc.publish_to_meshtastic_channel("hello") is False


def test_publish_success(monkeypatch):
    mc = MqttClientHandler()
    mc.connected = True

    def mock_publish(topic, payload, qos=1):
        # Validate payload is JSON and contains expected keys
        data = json.loads(payload)
        assert data.get("type") == "text"
        assert "payload" in data
        return DummyPubResult(rc=0)

    monkeypatch.setattr(mc.client, "publish", mock_publish)
    assert mc.publish_to_meshtastic_channel("hello") is True
