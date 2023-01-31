"""Define API client to interact with the Vaillant API."""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, cast

from aiohttp import ClientSession, ClientTimeout
from aiohttp.client_exceptions import ClientError

from .const import (
    DEFAULT_API_VERSION,
    LOGGER,
    HOST_API,
    HOST_APP,
    APP_ID,
    DEFAULT_USER_AGENT,
)
from .errors import RequestError, InvalidAuthError, RequestError, InvalidCredentialsError
from .model import Token, Device

DEFAULT_LIMIT = 288
DEFAULT_TIMEOUT = 20


class VaillantApiClient:
    """Define the API client."""

    def __init__(
        self,
        *,
        application_id: str = APP_ID,
        user_agent: str = DEFAULT_USER_AGENT,
        api_version: str = DEFAULT_API_VERSION,
        logger: logging.Logger = LOGGER,
        session: ClientSession | None = None,
    ) -> None:
        """Initialize.

        Args:
            application_id: .
            api_version: The version of the API to query.
            logger: The logger to use.
            session: An optional aiohttp ClientSession.
        """
        self._application_id: str = application_id
        self._api_version: str = api_version
        self._user_agent: str = user_agent
        self._logger = logger
        self._session: ClientSession = session or self._new_session()

    def _new_session(self) -> ClientSession:
        return ClientSession(
            timeout=ClientTimeout(total=DEFAULT_TIMEOUT),
            raise_for_status=False,
        )

    async def _request(
        self, method: str, url: str, **kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        """Make a request against the API.

        Args:
            method: An HTTP method.
            url: A relative API endpoint.
            **kwargs: Additional kwargs to send with the request.

        Returns:
            An API response payload.

        Raises:
            RequestError: Raised upon an underlying HTTP error.
        """

        kwargs.setdefault("params", {})
        kwargs.setdefault("headers", {})

        if use_running_session := self._session and not self._session.closed:
            session = self._session
        else:
            session = self._new_session()

        try:
            async with session.request(method, url, **kwargs) as resp:
                data = {}
                if 399 < resp.status and 500 > resp.status:
                    raise InvalidAuthError
                elif 200 == resp.status:
                    data = await resp.json(content_type=None)
                else:
                    resp.raise_for_status()
        except ClientError as err:
            raise RequestError(f"Error requesting data from {url}: {err}") from err
        finally:
            if not use_running_session:
                await session.close()

        self._logger.debug("Received data for %s: %s", url, data)

        return cast(dict[str, Any], data)

    async def login(self, username: str, password: str) -> Token:
        """Login to get uid and token."""
        data = {
            "appKey": self._application_id,
            "version": self._api_version,
            "data": {"username": username, "password": password},
        }
        headers = {
            "User-Agent": self._user_agent,
            "Referer": "http://localhost/main.html",
            "X-Requested-With": "com.vaillant.plus",
            "Origin": "http://localhost",
        }
        resp = await self._request(
            "post", f"{HOST_APP}/app/user/login", json=data, headers=headers
        )
        if resp is None or resp["code"] != "200" or resp["data"] is None:
            raise InvalidCredentialsError

        return Token(
            app_id=self._application_id,
            username=username,
            password=password,
            token=resp["data"]["token"],
            uid=resp["data"]["uid"],
        )

    async def get_device_list(self, token: str) -> list[Device]:
        """Get device list."""
        headers = {
            "User-Agent": "GizWifiSDK (v13.21121715)",
            "X-Gizwits-Application-Id": self._application_id,
            "X-Gizwits-User-token": token,
        }
        resp = await self._request(
            "get",
            f"{HOST_API}/app/bindings?show_disabled=0&limit=20&skip=0",
            headers=headers,
        )
        if resp.get("error_code") is not None:
            raise RequestError
        return [
            Device(
                id=d.get("did"),
                mac=d.get("mac"),
                product_key=d.get("product_key"),
                product_name=d.get("product_name"),
                host=d.get("host"),
                ws_port=d.get("ws_port"),
                wss_port=d.get("wss_port"),
                wifi_soft_version=d.get("wifi_soft_version", ""),
                wifi_hard_version=d.get("wifi_hard_version", ""),
                mcu_soft_version=d.get("mcu_soft_version", ""),
                mcu_hard_version=d.get("mcu_hard_version", ""),
                is_online=d.get("is_online"),
            )
            for d in resp["devices"]
        ]

    async def get_device_info(self, token: str, mac_addr: str) -> dict[str, str]:
        """Get device info"""
        headers = {
            "Authorization": token,
            "Version": self._api_version,
            "User-Agent": self._user_agent,
            "Referer": "http://localhost/main.html",
            "X-Requested-With": "com.vaillant.plus",
            "Origin": "http://localhost",
        }
        upper_mac = str.upper(mac_addr)
        resp = await self._request(
            "get",
            f"{HOST_APP}/app/device/sn/status?mac={upper_mac}",
            headers=headers,
        )
        code = resp.get("code", 0)
        if code == "505":
            raise InvalidAuthError

        if code != "200" or resp["data"] is None:
            raise RequestError

        return {
            "sno": resp["data"]["sno"],
            "mac": resp["data"]["mac"],
            "device_id": resp["data"]["gizDid"],
            "serial_number": resp["data"]["serialNumber"],
            "model": resp["data"]["model"],
            "status_code": resp["data"]["status"],
        }
