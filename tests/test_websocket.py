"""Define tests for the API."""

import pytest
import aiohttp
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock
from aiohttp import web
from typing import (
    Any
)

from vaillant_plus_cn_api import VaillantWebsocketClient
from vaillant_plus_cn_api.model import Token, Device
from vaillant_plus_cn_api.const import STATE_STOPPED, EVT_DEVICE_ATTR_UPDATE
from vaillant_plus_cn_api.errors import InvalidAuthError, WebsocketServerClosedConnectionError
from .conftest import TEST_USERNAME, TEST_PASSWORD, FakeWebsocketServer


def get_mock_device(websocket_server: FakeWebsocketServer) -> Device:
    return Device(
        id="1",
        mac="abcd123456",
        product_key="test_prd_key",
        product_id=3,
        product_name="test_prd_name",
        product_verbose_name="威能温控器",
        is_online=True,
        is_manager=True,
        group_id=2,
        sno="s1",
        create_time="2000-01-01 00:00:00",
        last_offline_time="2000-12-31 00:00:00",
        model_alias="两用炉",
        model="model1",
        serial_number="sn6",
        services_count=0,
    )


def get_mock_token() -> Token:
    return Token("appid_test", TEST_USERNAME,
                 TEST_PASSWORD, "token_test", "uid_test")


def get_client(websocket_server: FakeWebsocketServer, session: aiohttp.ClientSession, **kwargs: Any):
    return VaillantWebsocketClient(
        token=get_mock_token(),
        device=get_mock_device(websocket_server),
        api_host="127.0.0.1",
        port=websocket_server.port,
        session=session,
        use_ssl=False,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_client_endpoint(websocket_server: FakeWebsocketServer) -> None:
    """Test the websocket client generates correct endpoint.
    """
    async with aiohttp.ClientSession() as session:
        client = get_client(websocket_server, session)

        assert client._endpoint.startswith("ws://") is True


@pytest.mark.asyncio
async def test_client_endpoint_ssl(websocket_server: FakeWebsocketServer) -> None:
    """Test the websocket client generates correct endpoint.
    """
    async with aiohttp.ClientSession() as session:
        client = VaillantWebsocketClient(
            token=get_mock_token(),
            device=get_mock_device(websocket_server),
            session=session,
            use_ssl=True,
        )

        assert client._endpoint.startswith("wss://") is True


# @pytest.mark.asyncio
# async def test_websocket_invalid_auth_error(websocket_server: FakeWebsocketServer) -> None:
#     """Test the websocket client raising an invalid auth exception when login failed.
#     """

#     async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
#         cmd = data.get("cmd", "")
#         if cmd == "login_req":
#             await ws.send_json({
#                 "cmd": "login_res",
#                 "data": {
#                     "success": False
#                 }
#             })

#     websocket_server.add_handler(message_handler)

#     async with aiohttp.ClientSession() as session:
#         client = get_client(websocket_server, session)

#         with pytest.raises(InvalidAuthError):
#             await client.listen()

@pytest.mark.asyncio
async def test_websocket_login(websocket_server: FakeWebsocketServer) -> None:
    """Test the websocket client login process.
    """

    async with aiohttp.ClientSession() as session:
        client = get_client(websocket_server, session)

        actual = {
            "data": {}
        }

        async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
            msg_type = data.get("type", "")
            if msg_type == "msg":
                actual["data"] = data
                await client.close()
                await ws.close()

        websocket_server.add_handler(message_handler)

        await client.listen()

        assert actual["data"]["type"] == "msg"
        assert actual["data"]["productKey"] == "test_prd_key"
        assert actual["data"]["mac"] == "abcd123456"
        assert actual["data"]["did"] == "1"

@pytest.mark.asyncio
async def test_websocket_login_wait_for_login_response(websocket_server: FakeWebsocketServer) -> None:
    """Test the websocket client should wait for login response.
    """

    async with aiohttp.ClientSession() as session:
        client = get_client(websocket_server, session)

        actual = {
            "data": ""
        }

        async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
            msg_type = data.get("type", "")
            if msg_type == "msg":
                actual["data"] = data.get("did", "")
                await ws.send_json({
                    "type": "2",
                    "data": {
                        "DHW_setpoint": 45
                    },
                })
                await client.close()
                await ws.close()

        websocket_server.add_handler(message_handler)

        await client.listen()

        assert actual["data"] == "1"

@pytest.mark.asyncio
async def test_websocket_msg_not_handled_when_state_stopped(websocket_server: FakeWebsocketServer) -> None:
    """Test the websocket client will not trigger update handler if state is stopped.
    """

    async with aiohttp.ClientSession() as session:
        client = get_client(websocket_server, session)

        async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
            cmd = data.get("type", "")
            if cmd == "msg":
                client._state = STATE_STOPPED
                await asyncio.sleep(0.3)
                await ws.send_json({
                    "type": "2",
                    "data": {
                        "DHW_setpoint": 45
                    }
                })
                await asyncio.sleep(0.3)
                await client.close()
                await ws.close()

        websocket_server.add_handler(message_handler)

        on_update = AsyncMock()
        client.async_on_update(on_update)

        await client.listen()

        on_update.assert_not_called()

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
            cmd = data.get("type", "")
            if cmd == "msg":
                await asyncio.sleep(0.3)
                await ws.send_json({
                    "type": "2",
                    "did": "1",
                    "data": {
                        "DHW_setpoint": 46
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
        
        assert actual["subscribe"]["DHW_setpoint"] == 46
        assert actual["update"]["event"] == EVT_DEVICE_ATTR_UPDATE
        assert actual["update"]["data"]["DHW_setpoint"] == 46

@pytest.mark.asyncio
async def test_websocket_async_events(websocket_server: FakeWebsocketServer) -> None:
    """Test the client update event only triggers last async handler.
    """

    async with aiohttp.ClientSession() as session:

        client = get_client(websocket_server, session)

        async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
            cmd = data.get("type", "")
            if cmd == "msg":
                await asyncio.sleep(0.3)
                await ws.send_json({
                    "type": "2",
                    "did": "1",
                    "data": {
                        "DHW_setpoint": 50,
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
            "DHW_setpoint": 50,
        })

        on_update.assert_awaited_once_with(EVT_DEVICE_ATTR_UPDATE, {
            "data": {
                "DHW_setpoint": 50,
            }
        })

        on_update_old.assert_not_called()

@pytest.mark.asyncio
async def test_websocket_events(websocket_server: FakeWebsocketServer) -> None:
    """Test the client update event only triggers last sync handler.
    """

    async with aiohttp.ClientSession() as session:

        client = get_client(websocket_server, session)

        async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
            cmd = data.get("type", "")
            if cmd == "msg":
                await asyncio.sleep(0.3)
                await ws.send_json({
                    "type": "2",
                    "did": "1",
                    "data": {
                        "DHW_setpoint": 51,
                    }
                })
                await asyncio.sleep(0.3)
                await client.close()
                await ws.close()

        websocket_server.add_handler(message_handler)

        on_subscribe = MagicMock()
        on_update_old = MagicMock()
        on_update = MagicMock()

        client.on_subscribe(on_subscribe)
        client.on_update(on_update_old)
        client.on_update(on_update)

        await client.listen()

        on_subscribe.assert_called_once_with({
            "DHW_setpoint": 51,
        })

        on_update.assert_called_once_with(EVT_DEVICE_ATTR_UPDATE, {
            "data": {
                "DHW_setpoint": 51,
            }
        })

        on_update_old.assert_not_called()

@pytest.mark.asyncio
async def test_websocket_async_subscribed_event(websocket_server: FakeWebsocketServer) -> None:
    """Test the client only trigger subscribe event once.
    """

    async with aiohttp.ClientSession() as session:

        client = get_client(websocket_server, session)

        async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
            cmd = data.get("type", "")
            if cmd == "msg":
                await asyncio.sleep(0.3)
                await ws.send_json({
                    "type": "2",
                    "did": "1",
                    "data": {
                        "DHW_setpoint": 53,
                    }
                })
                await asyncio.sleep(0.3)
                await ws.send_json({
                    "type": "2",
                    "did": "1",
                    "data": {
                        "DHW_setpoint": 54,
                    }
                })
                await asyncio.sleep(0.3)
                await client.close()
                await ws.close()

        websocket_server.add_handler(message_handler)

        on_subscribe = AsyncMock()
        on_update = AsyncMock()

        client.async_on_subscribe(on_subscribe)
        client.async_on_update(on_update)

        await client.listen()

        on_subscribe.assert_awaited_once_with({
            "DHW_setpoint": 53,
        })

        on_update.assert_awaited_with(EVT_DEVICE_ATTR_UPDATE, {
            "data": {
                "DHW_setpoint": 54,
            }
        })

@pytest.mark.asyncio
async def test_websocket_subscribed_event(websocket_server: FakeWebsocketServer) -> None:
    """Test the client only trigger subscribe event once.
    """

    async with aiohttp.ClientSession() as session:

        client = get_client(websocket_server, session)

        async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
            cmd = data.get("type", "")
            if cmd == "msg":
                await asyncio.sleep(0.3)
                await ws.send_json({
                    "type": "2",
                    "did": "1",
                    "data": {
                        "DHW_setpoint": 53,
                    }
                })
                await asyncio.sleep(0.3)
                await ws.send_json({
                    "type": "2",
                    "did": "1",
                    "data": {
                        "DHW_setpoint": 54,
                    }
                })
                await asyncio.sleep(0.3)
                await client.close()
                await ws.close()

        websocket_server.add_handler(message_handler)

        on_subscribe = MagicMock()
        on_update = MagicMock()

        client.on_subscribe(on_subscribe)
        client.on_update(on_update)

        await client.listen()

        on_subscribe.assert_called_once_with({
            "DHW_setpoint": 53,
        })

        on_update.assert_called_with(EVT_DEVICE_ATTR_UPDATE, {
            "data": {
                "DHW_setpoint": 54,
            }
        })

@pytest.mark.asyncio
async def test_websocket_events_for_unmatched_device(websocket_server: FakeWebsocketServer) -> None:
    """Test the client will not trigger events if device id not matched.
    """

    async with aiohttp.ClientSession() as session:

        client = get_client(websocket_server, session)

        async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
            cmd = data.get("type", "")
            if cmd == "msg":
                await asyncio.sleep(0.3)
                await ws.send_json({
                    "type": "2",
                    "did": "2",
                    "data": {
                        "DHW_setpoint": 52,
                    }
                })
                await asyncio.sleep(0.3)
                await client.close()
                await ws.close()

        websocket_server.add_handler(message_handler)

        on_subscribe = AsyncMock()
        on_update = AsyncMock()

        client.async_on_subscribe(on_subscribe)
        client.async_on_update(on_update)

        await client.listen()

        on_subscribe.assert_not_called()
        on_update.assert_not_called()


@pytest.mark.asyncio
async def test_websocket_events_not_bind(websocket_server: FakeWebsocketServer) -> None:
    """Test the client will not trigger events if no handler provided.
    """

    async with aiohttp.ClientSession() as session:

        client = get_client(websocket_server, session)

        async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
            cmd = data.get("type", "")
            if cmd == "msg":
                await asyncio.sleep(0.3)
                await ws.send_json({
                    "type": "2",
                    "did": "2",
                    "data": {
                        "DHW_setpoint": 52,
                    }
                })
                await asyncio.sleep(0.3)
                await client.close()
                await ws.close()

        websocket_server.add_handler(message_handler)

        await client.listen()

        # assert client._async_on_subscribe_handler is None
        assert client._async_on_update_handler is None


# @pytest.mark.asyncio
# async def test_websocket_invalid_msg(websocket_server: FakeWebsocketServer) -> None:
#     """Test the client will fail when received an invalid message.
#     """

#     async with aiohttp.ClientSession() as session:
#         client = get_client(websocket_server, session, max_retry_attemps=1)

#         async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
#             cmd = data.get("type", "")
#             if cmd == "msg":
#                 await asyncio.sleep(0.3)
#                 await ws.send_json({
#                     "cmd": "s2c_invalid_msg",
#                     "data": {
#                         "error_code": 1009
#                     }
#                 })

#         websocket_server.add_handler(message_handler)

#         await client.listen()

#         assert client._failed_attempts == 1

# @pytest.mark.asyncio
# async def test_websocket_invalid_msg_other_codes(websocket_server: FakeWebsocketServer) -> None:
#     """Test the client received an invalid message.
#     """

#     async with aiohttp.ClientSession() as session:
#         client = get_client(websocket_server, session, max_retry_attemps=1)

#         state = ""

#         async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
#             cmd = data.get("cmd", "")
#             if cmd == "login_req":
#                 await ws.send_json({
#                     "cmd": "login_res",
#                     "data": {
#                         "success": True
#                     }
#                 })
#             elif cmd == "c2s_read":
#                 await asyncio.sleep(0.3)
#                 await ws.send_json({
#                     "cmd": "s2c_invalid_msg",
#                     "data": {
#                         "error_code": 1010
#                     }
#                 })
#                 if client.state != STATE_STOPPED:
#                     nonlocal state
#                     state = "still_connected"
                
#                 await asyncio.sleep(0.3)
#                 await client.close()
#                 await ws.close()

#         websocket_server.add_handler(message_handler)

#         await client.listen()

#         assert state == "still_connected"

# @pytest.mark.asyncio
# async def test_websocket_send_command(websocket_server: FakeWebsocketServer, event_loop: asyncio.AbstractEventLoop) -> None:
#     """Test the client raising an exception upon server error.
#     """

#     async with aiohttp.ClientSession() as session:
#         client = get_client(websocket_server, session)
#         task = event_loop.create_task(client.listen())

#         actual = {
#             "data": {}
#         }

#         async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
#             cmd = data.get("cmd", "")
#             if cmd == "login_req":
#                 await ws.send_json({
#                     "cmd": "login_res",
#                     "data": {
#                         "success": True
#                     }
#                 })
#             elif cmd == "c2s_write":
#                 actual["data"] = data["data"]["attr"]
#                 task.cancel()
#                 await client.close()
#                 await ws.close()

#         websocket_server.add_handler(message_handler)

#         await asyncio.sleep(0.3)
#         await client.send_command("c2s_write", {
#             "attr": "test"
#         })
#         await asyncio.sleep(0.3)
#         assert actual["data"] == "test"


# @pytest.mark.asyncio
# async def test_websocket_send_command_check_state(websocket_server: FakeWebsocketServer, event_loop: asyncio.AbstractEventLoop) -> None:
#     """Test the websocket client checks the state before sending command.
#     """

#     async with aiohttp.ClientSession() as session:
#         client = get_client(websocket_server, session)

#         event_loop.call_later(
#           0.3,
#           lambda: asyncio.create_task(client.close())
#         )

#         actual = {
#             "data": ""
#         }

#         async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
#             cmd = data.get("cmd", "")
#             if cmd == "login_req":
#                 await ws.send_json({
#                     "cmd": "login_res",
#                     "data": {
#                         "success": True
#                     }
#                 })
#             elif cmd == "c2s_write":
#                 actual["data"] = "value_received"

#         websocket_server.add_handler(message_handler)

#         await client.listen()
#         await client.send_command("c2s_write", {
#             "attr": "test"
#         })
#         await asyncio.sleep(0.3)
#         assert actual["data"] == ""


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
            cmd = data.get("type", "")
            if cmd == "msg":
                await ws.send_json({
                    "type": "2",
                    "did": "1",
                    "data": {
                        "DHW_setpoint": 50,
                    }
                })
            elif cmd == "ping":
                actual["pinged"] = True
                await client.close()
                await ws.close()

        websocket_server.add_handler(message_handler)

        await client.listen()

        assert actual["pinged"] is True

@pytest.mark.asyncio
async def test_websocket_heartbeat_trigger(websocket_server: FakeWebsocketServer, event_loop: asyncio.AbstractEventLoop) -> None:
    """Test the client can trigger another heartbeat when received pong from server.
    """

    async with aiohttp.ClientSession() as session:
        client = get_client(websocket_server, session, heartbeat_interval=2)

        actual = {
            "pinged": 0
        }

        async def message_handler(data: dict[str, Any], ws: web.WebSocketResponse):
            cmd = data.get("type", "")
            if cmd == "msg":
                await ws.send_json({
                    "type": "2",
                    "did": "1",
                    "data": {
                        "DHW_setpoint": 50,
                    }
                })
            elif cmd == "ping":
                actual["pinged"] += 1
                await ws.send_json({
                    "type": "pong",
                })

        websocket_server.add_handler(message_handler)

        event_loop.call_later(
          4.3,
          lambda: asyncio.create_task(client.close())
        )

        await client.listen()

        assert actual["pinged"] == 2

# @pytest.mark.asyncio
# async def test_websocket_close_ignore_client_exception(websocket_server: FakeWebsocketServer, caplog) -> None:
#     """Test the client ignored ws_client exception when close connection.
#     """

#     async with aiohttp.ClientSession() as session:
#         client = get_client(websocket_server, session)

#         client._ws_client = await session._ws_connect(f"ws://127.0.0.1:{websocket_server.port}/monitor/ws/app")
#         client._ws_client.close = AsyncMock(side_effect=Exception("error"))

#         caplog.set_level(logging.WARNING)
#         caplog.clear()
#         await client.close()

#         assert "Close websocket error" in caplog.text