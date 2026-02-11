import asyncio
import pytest

from bot import config
from app import health, MQTT_CLIENT


class DummyClient:
    def __init__(self, connected=True):
        self.connected = connected


@pytest.mark.asyncio
async def test_health_without_mqtt(monkeypatch):
    # Ensure MQTT client global is None
    monkeypatch.setattr('app.MQTT_CLIENT', None)
    # Create a dummy request object (minimal)
    class Req:
        pass

    resp = await health(Req())
    # `health` returns an aiohttp.web.Response; extract body bytes and parse JSON
    import json as _json
    body = resp.body or b"{}"
    data = _json.loads(body.decode("utf-8"))
    assert data["app"] == "ok"


@pytest.mark.asyncio
async def test_health_with_mqtt(monkeypatch):
    dummy = DummyClient(connected=True)
    monkeypatch.setattr('app.MQTT_CLIENT', dummy)
    class Req:
        pass

    resp = await health(Req())
    import json as _json
    body = resp.body or b"{}"
    data = _json.loads(body.decode("utf-8"))
    assert data["mqtt"]["connected"] is True
