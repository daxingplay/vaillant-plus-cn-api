"""Define an object to interact with the Websocket API."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from .const import API_HOST, APP_KEY, LOGGER, STATE_CONNECTING, STATE_STOPPED, STATE_CONNECTED, STATE_SUBSCRIBED, STATE_DISCONNECTED, EVT_DEVICE_ATTR_UPDATE
from .errors import InvalidTokenError, InvalidAuthError, WebsocketServerClosedConnectionError
from .model import Token, Device

DEFAULT_WATCHDOG_TIMEOUT = 15


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
        application_key: str = APP_KEY,
        api_host: str = API_HOST,
        port: int | None = None,
        logger: logging.Logger = LOGGER,
        session: aiohttp.ClientSession | None = None,
        use_ssl: bool = True,
        verify_ssl: bool = True,
        max_retry_attemps: int | None = None,
        heartbeat_interval: int = DEFAULT_WATCHDOG_TIMEOUT,
    ) -> None:
        """Initialize.

        Args:
            application_key: Application key.
            api_version: The version of the API to query.
            logger: The logger to use.
        """

        self._session: aiohttp.ClientSession = session or aiohttp.ClientSession()
        self._use_ssl = use_ssl
        self._verify_ssl = verify_ssl
        self._token = token
        self._device = device
        self._application_key = application_key
        self._async_on_subscribe_handler: Callable[[dict[str, Any]], Awaitable[None]] | None = None
        self._async_on_update_handler: Callable[..., Awaitable[None]] | None = None
        self._on_subscribe_handler: Callable[[dict[str, Any]], None] | None = None
        self._on_update_handler: Callable[..., None] | None = None
        self._logger = logger
        self._max_retry_attemps = max_retry_attemps
        self._state = None
        self._failed_attempts = 0
        self._ws_client: aiohttp.ClientWebSocketResponse | None = None
        self._watchdog = WebsocketWatchdog(logger, self.ping, timeout_seconds=heartbeat_interval)

        self._endpoint = ""
        endpoint = api_host.removeprefix("https://")
        if self._use_ssl:
            self._endpoint = f"wss://{endpoint}"
        else:
            self._endpoint = f"ws://{endpoint}"

        if port is not None:
            self._endpoint = f"{self._endpoint}:{port}"

    @property
    def state(self):
        """Return the current state."""
        return self._state

    async def connect(self) -> None:
        """Connect to websocket server."""
        
        self._state = STATE_CONNECTING

        try:
            async with self._session.ws_connect(
                f"{self._endpoint}/monitor/ws/app",
                verify_ssl=self._verify_ssl,
                headers={
                    "Authorization": f"Bearer {self._token.access_token}",
                },
            ) as ws_client:
                self._ws_client = ws_client

                await ws_client.send_json({
                    "type": "msg",
                    "productKey": self._device.product_key,
                    "mac": self._device.mac,
                    "did": self._device.id,
                })

                self._state = STATE_CONNECTED

                await self._watchdog.trigger()

                async for message in ws_client:
                    if self.state == STATE_STOPPED:
                        break

                    if message.type == aiohttp.WSMsgType.TEXT:
                        msg: dict = message.json()
                        msg_type = msg.get("type", "")
                        data = msg.get("data", {})

                        self._logger.debug("Recv: %s", message)

                        if msg_type == "2":
                            device_id = msg.get("did")
                            if device_id == self._device.id:
                                self._logger.debug(
                                    "Recv atrrs for device %s => %s", device_id, data)

                                if self.state != STATE_SUBSCRIBED:
                                    if self._async_on_subscribe_handler is not None:
                                        await self._async_on_subscribe_handler(data)
                                    elif self._on_subscribe_handler is not None:
                                        self._on_subscribe_handler(data)
                                self._state = STATE_SUBSCRIBED
                                
                                if self._async_on_update_handler is not None:
                                    await self._async_on_update_handler(EVT_DEVICE_ATTR_UPDATE, { "data": data })
                                elif self._on_update_handler is not None:
                                    self._on_update_handler(EVT_DEVICE_ATTR_UPDATE, { "data": data })
                        elif msg_type == "pong":
                            self._logger.debug("Recieved pong")
                            await self._watchdog.trigger()
                        else:
                            self._logger.info("Unhandled msg: %s", msg)

                    elif message.type == aiohttp.WSMsgType.CLOSE:
                        self._logger.warning("Websocket server closing: %s, %s", message.data, message.extra)
                    elif message.type == aiohttp.WSMsgType.CLOSED:
                        self._logger.warning(
                            "Websocket connection closed")
                        break

                    elif message.type == aiohttp.WSMsgType.ERROR:
                        self._logger.error("Websocket error")
                        break

        except InvalidTokenError as error:
            self._state = STATE_STOPPED
            self._logger.warning("Websocket server auth failed: %s", error)
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
        if self._ws_client is not None:
            await self._ws_client.close()

    async def ping(self) -> None:
        """Send ping to server."""
        if self._ws_client is not None:
            await self._ws_client.send_json({
                "type": "ping"
            })
        else:
            self._logger.error("Cannot send ping")

    def async_on_subscribe(self, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        self._async_on_subscribe_handler = handler

    def async_on_update(self, handler: Callable[..., Awaitable[None]]) -> None:
        self._async_on_update_handler = handler

    def on_subscribe(self, handler: Callable[[dict[str, Any]], None]) -> None:
        self._on_subscribe_handler = handler

    def on_update(self, handler: Callable[..., None]) -> None:
        self._on_update_handler = handler