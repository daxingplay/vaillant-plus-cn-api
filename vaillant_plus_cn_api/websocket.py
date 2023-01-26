"""Define an object to interact with the Websocket API."""
from __future__ import annotations

import asyncio
import logging
import json
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from .const import DEFAULT_API_VERSION, APP_ID, LOGGER, DEFAULT_USER_AGENT, STATE_CONNECTING, STATE_STOPPED, STATE_CONNECTED, STATE_SUBSCRIBED, STATE_DISCONNECTED
from .errors import WebsocketError, InvalidAuthError, WebsocketServerClosedConnectionError
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
        self._logger.info("Watchdog expired – calling %s",
                          self._action.__name__)
        await self._action()

    async def trigger(self) -> None:
        """Trigger the watchdog."""
        self._logger.info(
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
        verify_ssl: bool = True,
        max_retry_attemps: int | None = None,
    ) -> None:
        """Initialize.

        Args:
            application_key: An Ambient Weather application key.
            api_key: An Ambient Weather API key.
            api_version: The version of the API to query.
            logger: The logger to use.
        """

        self._session: aiohttp.ClientSession = session or aiohttp.ClientSession()
        self._verify_ssl = verify_ssl
        self._token = token
        self._device = device
        self._application_id = application_id
        self._api_version = api_version
        self._async_user_connect_handler: Callable[...,
                                                   Awaitable[None]] | None = None
        self._logger = logger
        self._max_retry_attemps = max_retry_attemps
        self._state = None
        # self._ws_client = None
        self._watchdog = WebsocketWatchdog(logger, self.ping)

    @property
    def state(self):
        """Return the current state."""
        return self._state

    async def connect(self) -> None:
        self._state = STATE_CONNECTING

        try:
            async with self._session.ws_connect(
                f"wss://{self._device.host}:{self._device.wss_port}/ws/app/v1",
                verify_ssl=self._verify_ssl,
                headers={
                    "User-Agent": DEFAULT_USER_AGENT,
                },
            ) as ws_client:
                self._ws_client = ws_client
                self._failed_attempts = 0

                await ws_client.send_json({
                    "cmd": "login_req",
                    "data": {
                        "appid": self._token.app_id or self._application_id,
                        "uid": self._token.uid,
                        "token": self._token,
                        "p0_type": "attrs_v4",
                        "heartbeat_interval": 180,
                        "auto_subscribe": False,
                    },
                })

                login_ret = await ws_client.receive_json()
                if login_ret["cmd"] != "login_res" or login_ret["data"]["success"] is not True:
                    self._logger.error("login failed")
                    self._state = STATE_STOPPED
                    raise InvalidAuthError

                await ws_client.send_json({"cmd": "subscribe_req", "data": [{"did": self._device.id}]})
                await ws_client.send_json({"cmd": "c2s_read", "data": {"did": self._device.id}})

                self._state = STATE_CONNECTED

                async for message in ws_client:
                    if self.state == STATE_STOPPED:
                        break

                    if message.type == aiohttp.WSMsgType.TEXT:
                        msg = message.json()
                        cmd = msg["cmd"]
                        data = msg["data"]

                        self._logger.debug("Recv: %s", msg)

                        if cmd == "s2c_noti":
                            if data["did"] == self._device.id:
                                device_attrs = data["attrs"]
                                self._logger.debug("Recv atrrs for device %s => %s", data["did"], device_attrs)
                                if self.state != STATE_SUBSCRIBED:
                                    # TODO trigger subscribe event
                                    self._state = STATE_SUBSCRIBED
                                # TODO trigger device attr update event
                        elif cmd == "pong":
                            await self._watchdog.trigger()
                        elif cmd == "s2c_invalid_msg":
                            error_code = data["error_code"]
                            if error_code == 1009:
                                raise WebsocketServerClosedConnectionError
                        else:
                            self._logger.info("Unhandled msg: %s", msg)

                    elif message.type == aiohttp.WSMsgType.CLOSED:
                        self._logger.warning("AIOHTTP websocket connection closed")
                        break

                    elif message.type == aiohttp.WSMsgType.ERROR:
                        self._logger.error("AIOHTTP websocket error")
                        break

        except aiohttp.ClientResponseError as error:
            if error.code == 401:
                self._logger.error("Credentials rejected: %s", error)
            else:
                self._logger.error("Unexpected response received: %s", error)
            self._state = STATE_STOPPED
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as error:
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
                self._logger.exception("Unexpected exception occurred: %s", error)
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

    def close(self):
        """Close the listening websocket."""
        self._state = STATE_STOPPED
        self._watchdog.cancel()

    async def ping(self) -> None:
        """Send ping to server."""
        await self.send_command("ping")

    async def send_command(self, cmd: str, data: dict[str, Any] | None = None) -> None:
        if self.state != STATE_STOPPED and self._ws_client is not None:
            msg: dict[str, Any] = {
                "cmd": cmd
            }
            if data is not None:
                msg["data"] = data

            await self._ws_client.send_json(msg)
