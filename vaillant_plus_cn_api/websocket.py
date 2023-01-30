"""Define an object to interact with the Websocket API."""
from __future__ import annotations

import asyncio
import logging
import json
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from .const import DEFAULT_API_VERSION, APP_ID, LOGGER, DEFAULT_USER_AGENT, STATE_CONNECTING, STATE_STOPPED, STATE_CONNECTED, STATE_SUBSCRIBED, STATE_DISCONNECTED, EVT_DEVICE_ATTR_UPDATE
from .errors import InvalidTokenError, InvalidAuthError, WebsocketServerClosedConnectionError
from .model import Token, Device

DEFAULT_WATCHDOG_TIMEOUT = 30


class WebsocketWatchdog:
    """Define a watchdog to kick the websocket connection at intervals."""

    def __init__(
        self,
        logger: logging.Logger,
        action: Callable[..., Awaitable],
        *,
        timeout_seconds: int = DEFAULT_WATCHDOG_TIMEOUT,
    ):
        """Initialize.

        Args:
            logger: The logger to use.
            action: The coroutine function to call when the watchdog expires.
            timeout_seconds: The number of seconds before the watchdog times out.
        """
        self._action = action
        self._logger = logger
        self._loop = asyncio.get_event_loop()
        self._timeout = timeout_seconds
        self._timer_task: asyncio.TimerHandle | None = None

    def cancel(self) -> None:
        """Cancel the watchdog."""
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None

    async def on_expire(self) -> None:
        """Log and act when the watchdog expires."""
        self._logger.debug("Watchdog expired – calling %s",
                          self._action.__name__)
        await self._action()

    async def trigger(self) -> None:
        """Trigger the watchdog."""
        self._logger.debug(
            "Watchdog triggered – sleeping for %s seconds", self._timeout)

        if self._timer_task:
            self._timer_task.cancel()

        self._timer_task = self._loop.call_later(
            self._timeout, lambda: asyncio.create_task(self.on_expire())
        )


class VaillantWebsocketClient:  # pylint: disable=too-many-instance-attributes
    """Define the websocket client."""

    def __init__(
        self,
        token: Token,
        device: Device,
        *,
        application_id: str = APP_ID,
        api_version: str = DEFAULT_API_VERSION,
        logger: logging.Logger = LOGGER,
        session: aiohttp.ClientSession | None = None,
        use_ssl: bool = True,
        verify_ssl: bool = True,
        max_retry_attemps: int | None = None,
        heartbeat_interval: int = DEFAULT_WATCHDOG_TIMEOUT,
    ) -> None:
        """Initialize.

        Args:
            application_key: An Ambient Weather application key.
            api_key: An Ambient Weather API key.
            api_version: The version of the API to query.
            logger: The logger to use.
        """

        self._session: aiohttp.ClientSession = session or aiohttp.ClientSession()
        self._use_ssl = use_ssl
        self._verify_ssl = verify_ssl
        self._token = token
        self._device = device
        self._application_id = application_id
        self._api_version = api_version
        self._async_on_subscribe_handler: Callable[[dict[str, Any]], Awaitable[None]] | None = None
        self._async_on_update_handler: Callable[..., Awaitable[None]] | None = None
        self._on_subscribe_handler: Callable[[dict[str, Any]], None] | None = None
        self._on_update_handler: Callable[..., None] | None = None
        self._logger = logger
        self._max_retry_attemps = max_retry_attemps
        self._state = None
        # self._ws_client = None
        self._watchdog = WebsocketWatchdog(logger, self.ping, timeout_seconds=heartbeat_interval)

        self._endpoint = f"ws://{self._device.host}:{self._device.ws_port}"
        if self._use_ssl:
            self._endpoint = f"wss://{self._device.host}:{self._device.wss_port}"

    @property
    def state(self):
        """Return the current state."""
        return self._state

    async def connect(self) -> None:
        self._state = STATE_CONNECTING

        try:
            async with self._session.ws_connect(
                f"{self._endpoint}/ws/app/v1",
                verify_ssl=self._verify_ssl,
                headers={
                    "User-Agent": DEFAULT_USER_AGENT,
                },
            ) as ws_client:
                self._ws_client = ws_client

                await ws_client.send_json({
                    "cmd": "login_req",
                    "data": {
                        "appid": self._token.app_id or self._application_id,
                        "uid": self._token.uid,
                        "token": self._token.token,
                        "p0_type": "attrs_v4",
                        "heartbeat_interval": 180,
                        "auto_subscribe": False,
                    },
                })

                login_ret = await ws_client.receive_json()
                if login_ret["cmd"] != "login_res" or login_ret["data"]["success"] is not True:
                    self._logger.error("login failed")
                    self._state = STATE_STOPPED
                    raise InvalidTokenError

                await ws_client.send_json({"cmd": "subscribe_req", "data": [{"did": self._device.id}]})
                await ws_client.send_json({"cmd": "c2s_read", "data": {"did": self._device.id}})

                self._state = STATE_CONNECTED

                await self._watchdog.trigger()

                async for message in ws_client:
                    if self.state == STATE_STOPPED:
                        break

                    if message.type == aiohttp.WSMsgType.TEXT:
                        msg: dict = message.json()
                        cmd = msg.get("cmd", "")
                        data = msg.get("data", {})

                        self._logger.debug("Recv: %s", message)

                        if cmd == "s2c_noti":
                            if data["did"] == self._device.id:
                                device_attrs = data["attrs"]
                                self._logger.debug(
                                    "Recv atrrs for device %s => %s", data["did"], device_attrs)
                                if self.state != STATE_SUBSCRIBED:
                                    if self._async_on_subscribe_handler is not None:
                                        await self._async_on_subscribe_handler(device_attrs)
                                    elif self._on_subscribe_handler is not None:
                                        self._on_subscribe_handler(device_attrs)
                                    self._state = STATE_SUBSCRIBED
                                
                                if self._async_on_update_handler is not None:
                                    await self._async_on_update_handler(EVT_DEVICE_ATTR_UPDATE, { "data": device_attrs })
                                elif self._on_update_handler is not None:
                                    self._on_update_handler(EVT_DEVICE_ATTR_UPDATE, { "data": device_attrs })
                        elif cmd == "pong":
                            await self._watchdog.trigger()
                        elif cmd == "s2c_invalid_msg":
                            self._logger.error("Server pushed an error msg: %s", message)
                            error_code = data["error_code"]
                            # {'cmd': 's2c_invalid_msg', 'data': {'error_code': 1009, 'msg': 'M2M socket has closed, please login again!'}}
                            # {'cmd': 's2c_invalid_msg', 'data': {'error_code': 1011, 'msg': 'No heartbeat!'}}
                            # TODO: other error code should treat more gracefully.
                            if error_code == 1009 or error_code == 1011:
                                raise WebsocketServerClosedConnectionError
                        else:
                            self._logger.info("Unhandled msg: %s", msg)

                    elif message.type == aiohttp.WSMsgType.CLOSED:
                        self._logger.warning(
                            "AIOHTTP websocket connection closed")
                        break

                    elif message.type == aiohttp.WSMsgType.ERROR:
                        self._logger.error("AIOHTTP websocket error")
                        break

        except InvalidTokenError as error:
            self._state = STATE_STOPPED
            raise InvalidAuthError
        except aiohttp.ClientResponseError as error:
            if error.code == 401:
                self._logger.error("Credentials rejected: %s", error)
                raise InvalidAuthError
            else:
                self._logger.error("Unexpected response received: %s", error)
            self._state = STATE_STOPPED
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError, WebsocketServerClosedConnectionError) as error:
            if self._max_retry_attemps is not None and self._failed_attempts >= self._max_retry_attemps:
                self._logger.error("Too many retry attemps. exit.")
                self._state = STATE_STOPPED
            elif self.state != STATE_STOPPED:
                retry_delay = min(2 ** (self._failed_attempts - 1) * 10, 300)
                self._failed_attempts += 1
                self._logger.error(
                    "Websocket connection failed, retrying in %ds: %s",
                    retry_delay,
                    error,
                )
                self._state = STATE_DISCONNECTED
                await asyncio.sleep(retry_delay)
        except Exception as error:  # pylint: disable=broad-except
            if self.state != STATE_STOPPED:
                self._logger.exception(
                    "Unexpected exception occurred: %s", error)
                self._state = STATE_STOPPED
        else:
            if self.state != STATE_STOPPED:
                self._state = STATE_DISCONNECTED
                await asyncio.sleep(5)

    async def listen(self):
        """Start the listening websocket."""
        self._failed_attempts = 0
        while self.state != STATE_STOPPED:
            await self.connect()

    async def close(self):
        """Close the listening websocket."""
        self._state = STATE_STOPPED
        self._watchdog.cancel()
        try:
            await self._ws_client.close()
        except Exception as error:
            self._logger.warning("Close websocket error: %s", error)

    async def ping(self) -> None:
        """Send ping to server."""
        await self.send_command("ping")

    async def send_command(self, cmd: str, data: dict[str, Any] | None = None) -> None:
        if self.state != STATE_STOPPED and self.state != STATE_DISCONNECTED and self._ws_client is not None:
            msg: dict[str, Any] = {
                "cmd": cmd
            }
            if data is not None:
                msg["data"] = data

            await self._ws_client.send_json(msg)

    def async_on_subscribe(self, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        self._async_on_subscribe_handler = handler

    def async_on_update(self, handler: Callable[..., Awaitable[None]]) -> None:
        self._async_on_update_handler = handler

    def on_subscribe(self, handler: Callable[[dict[str, Any]], None]) -> None:
        self._on_subscribe_handler = handler

    def on_update(self, handler: Callable[..., None]) -> None:
        self._on_update_handler = handler