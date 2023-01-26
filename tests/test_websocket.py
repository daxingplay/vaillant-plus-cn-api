"""Define tests for the API."""

import pytest
import aiohttp
import asyncio
from unittest.mock import AsyncMock, MagicMock
from aiohttp import web
from typing import (
    Any
)

from vaillant_plus_cn_api import VaillantWebsocketClient
from vaillant_plus_cn_api.model import Token, Device
from vaillant_plus_cn_api.const import HOST_APP, STATE_STOPPED, EVT_DEVICE_ATTR_UPDATE
from vaillant_plus_cn_api.errors import InvalidAuthError, WebsocketServerClosedConnectionError
from .conftest import TEST_USERNAME, TEST_PASSWORD, FakeWebsocketServer


def get_client(websocket_server: FakeWebsocketServer, session: aiohttp.ClientSession, **kwargs: Any):
    return VaillantWebsocketClient(
        token=Token("appid_test", TEST_USERNAME,
                    TEST_PASSWORD, "token_test", "uid_test"),
        device=Device(
            id="1",
            mac="abcd123456",
            product_key="test_prd_key",
            product_name="test_prd_name",
            host="127.0.0.1",
            ws_port=websocket_server.port,  # type: ignore
            wss_port=0,
            wifi_soft_version="",
            wifi_hard_version="",
            mcu_soft_version="",
            mcu_hard_version="",
            is_online=True,
        ),
        session=session,
        use_ssl=False,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_websocket_invalid_auth_error(websocket_server: FakeWebsocketServer) -> None:
    """Test the API client raising an exception upon HTTP error.
    """

    async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
        cmd = data.get("cmd", "")
        if cmd == "login_req":
            await ws.send_json({
                "cmd": "login_res",
                "data": {
                    "success": False
                }
            })

    websocket_server.add_handler(message_handler)

    async with aiohttp.ClientSession() as session:
        client = get_client(websocket_server, session)

        with pytest.raises(InvalidAuthError):
            await client.listen()


@pytest.mark.asyncio
async def test_websocket_login(websocket_server: FakeWebsocketServer) -> None:
    """Test the API client login process.
    """

    async with aiohttp.ClientSession() as session:
        client = get_client(websocket_server, session)

        actual = {
          "data": {}
        }

        async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
            cmd = data.get("cmd", "")
            if cmd == "login_req":
                actual["data"] = data.get("data", {})
                await client.close()
                await ws.close()

        websocket_server.add_handler(message_handler)

        await client.listen()

        assert actual["data"]["appid"] == "appid_test"
        assert actual["data"]["uid"] == "uid_test"
        assert actual["data"]["token"] == "token_test"
        assert actual["data"]["p0_type"] == "attrs_v4"
        assert actual["data"]["heartbeat_interval"] == 180
        assert actual["data"]["auto_subscribe"] == False


@pytest.mark.asyncio
async def test_websocket_login_and_subscribed(websocket_server: FakeWebsocketServer) -> None:
    """Test the API client raising an exception upon HTTP error.
    """

    async with aiohttp.ClientSession() as session:
        client = get_client(websocket_server, session)

        actual = {
          "data": []
        }

        async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
            cmd = data.get("cmd", "")
            if cmd == "login_req":
                await ws.send_json({
                    "cmd": "login_res",
                    "data": {
                        "success": True
                    }
                })
            elif cmd == "subscribe_req":
                actual["data"] = data.get("data", [])
                await client.close()
                await ws.close()

        websocket_server.add_handler(message_handler)

        await client.listen()

        assert actual["data"][0]["did"] == "1"


@pytest.mark.asyncio
async def test_websocket_login_and_subscribed_and_read_data(websocket_server: FakeWebsocketServer) -> None:
    """Test the API client raising an exception upon HTTP error.
    """

    async with aiohttp.ClientSession() as session:
        client = get_client(websocket_server, session)

        actual = {
          "data": {}
        }

        async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
            cmd = data.get("cmd", "")
            if cmd == "login_req":
                await ws.send_json({
                    "cmd": "login_res",
                    "data": {
                        "success": True
                    }
                })
            elif cmd == "c2s_read":
                actual["data"] = data.get("data", {})
                await client.close()
                await ws.close()

        websocket_server.add_handler(message_handler)

        await client.listen()

        assert actual["data"]["did"] == "1"


@pytest.mark.asyncio
async def test_websocket_push_device_data(websocket_server: FakeWebsocketServer) -> None:
    """Test the client can receive data when server pushes new data.
    """

    async with aiohttp.ClientSession() as session:

        client = get_client(websocket_server, session)

        actual = {
          "subscribe": {},
          "update": {},
        }

        async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
            cmd = data.get("cmd", "")
            if cmd == "login_req":
                await ws.send_json({
                    "cmd": "login_res",
                    "data": {
                        "success": True
                    }
                })
            elif cmd == "c2s_read":
                await asyncio.sleep(0.3)
                await ws.send_json({
                    "cmd": "s2c_noti",
                    "data": {
                        "did": "1",
                        "attrs": {
                            "attr1": "test_attr1_v1",
                            "ATTR2": "test_attr2_v2",
                            "Attr_3": "test_attr3_v3"
                        }
                    }
                })
                await asyncio.sleep(0.3)
                await client.close()
                await ws.close()

        websocket_server.add_handler(message_handler)

        async def on_subscribe(device_attr: dict[str, Any]) -> None:
          actual["subscribe"] = device_attr

        async def on_update(event_name: str, data: dict[str, Any]) -> None:
          actual["update"] = {
            "event": event_name,
            "data": data["data"],
          }

        client.async_on_subscribe(on_subscribe)
        client.async_on_update(on_update)

        await client.listen()

        assert actual["subscribe"]["attr1"] == "test_attr1_v1"
        assert actual["subscribe"]["ATTR2"] == "test_attr2_v2"
        assert actual["subscribe"]["Attr_3"] == "test_attr3_v3"

        assert actual["update"]["event"] == EVT_DEVICE_ATTR_UPDATE
        assert actual["update"]["data"]["attr1"] == "test_attr1_v1"
        assert actual["update"]["data"]["ATTR2"] == "test_attr2_v2"
        assert actual["update"]["data"]["Attr_3"] == "test_attr3_v3"


@pytest.mark.asyncio
async def test_websocket_events(websocket_server: FakeWebsocketServer) -> None:
    """Test the client can receive data when server pushes new data.
    """

    async with aiohttp.ClientSession() as session:

        client = get_client(websocket_server, session)

        async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
            cmd = data.get("cmd", "")
            if cmd == "login_req":
                await ws.send_json({
                    "cmd": "login_res",
                    "data": {
                        "success": True
                    }
                })
            elif cmd == "c2s_read":
                await asyncio.sleep(0.3)
                await ws.send_json({
                    "cmd": "s2c_noti",
                    "data": {
                        "did": "1",
                        "attrs": {
                            "attr1": "test_attr1_v1",
                            "ATTR2": "test_attr2_v2",
                            "Attr_3": "test_attr3_v3"
                        }
                    }
                })
                await asyncio.sleep(0.3)
                await client.close()
                await ws.close()

        websocket_server.add_handler(message_handler)

        on_subscribe = AsyncMock()
        on_update_old = AsyncMock()
        on_update = AsyncMock()

        client.async_on_subscribe(on_subscribe)
        client.async_on_update(on_update_old)
        client.async_on_update(on_update)

        await client.listen()

        on_subscribe.assert_awaited_once_with({
            "attr1": "test_attr1_v1",
            "ATTR2": "test_attr2_v2",
            "Attr_3": "test_attr3_v3"
        })

        on_update.assert_awaited_once_with(EVT_DEVICE_ATTR_UPDATE, {
            "data": {
                "attr1": "test_attr1_v1",
                "ATTR2": "test_attr2_v2",
                "Attr_3": "test_attr3_v3"
            }
        })

        on_update_old.assert_not_called()


@pytest.mark.asyncio
async def test_websocket_invalid_msg(websocket_server: FakeWebsocketServer) -> None:
    """Test the client received an invalid message.
    """

    async with aiohttp.ClientSession() as session:
        client = get_client(websocket_server, session, max_retry_attemps=1)

        async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
            cmd = data.get("cmd", "")
            if cmd == "login_req":
                await ws.send_json({
                    "cmd": "login_res",
                    "data": {
                        "success": True
                    }
                })
            elif cmd == "c2s_read":
                await asyncio.sleep(0.3)
                await ws.send_json({
                    "cmd": "s2c_invalid_msg",
                    "data": {
                        "error_code": 1009
                    }
                })

        websocket_server.add_handler(message_handler)

        await client.listen()

        assert client._failed_attempts == 1


@pytest.mark.asyncio
async def test_websocket_send_command(websocket_server: FakeWebsocketServer, event_loop: asyncio.AbstractEventLoop) -> None:
    """Test the client raising an exception upon server error.
    """

    async with aiohttp.ClientSession() as session:
        client = get_client(websocket_server, session)
        task = event_loop.create_task(client.listen())

        actual = {
          "data": {}
        }

        async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
            cmd = data.get("cmd", "")
            if cmd == "login_req":
                await ws.send_json({
                    "cmd": "login_res",
                    "data": {
                        "success": True
                    }
                })
            elif cmd == "c2s_write":
                actual["data"] = data["data"]["attr"]
                task.cancel()
                await client.close()
                await ws.close()

        websocket_server.add_handler(message_handler)

        await asyncio.sleep(0.3)
        await client.send_command("c2s_write", {
            "attr": "test"
        })
        await asyncio.sleep(0.3)
        assert actual["data"] == "test"


@pytest.mark.asyncio
async def test_websocket_heartbeat(websocket_server: FakeWebsocketServer) -> None:
    """Test the client heartbeat.
    """

    async with aiohttp.ClientSession() as session:
        client = get_client(websocket_server, session, heartbeat_interval=2)

        actual = {
          "pinged": False
        }

        async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
            cmd = data.get("cmd", "")
            if cmd == "login_req":
                await ws.send_json({
                    "cmd": "login_res",
                    "data": {
                        "success": True
                    }
                })
            elif cmd == "ping":
                actual["pinged"] = True
                await client.close()
                await ws.close()

        websocket_server.add_handler(message_handler)

        await client.listen()

        assert actual["pinged"] == True