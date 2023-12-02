"""Define API client to interact with the Vaillant API."""
from __future__ import annotations

import logging
from typing import Any, cast

from aiohttp import ClientSession, ClientTimeout, FormData
from aiohttp.client_exceptions import ClientError

from .const import (
    LOGGER,
    API_HOST,
    APP_KEY,
    APP_AUTH,
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
        app_key: str = APP_KEY,
        app_auth: str = APP_AUTH,
        user_agent: str = DEFAULT_USER_AGENT,
        logger: logging.Logger = LOGGER,
        session: ClientSession | None = None,
    ) -> None:
        """Initialize.

        Args:
            app_key: App key.
            app_auth: The username & password combination for authorization.
            logger: The logger to use.
            session: An optional aiohttp ClientSession.
        """
        self._application_key: str = app_key
        self._application_auth: str = app_auth
        self._access_token: str = ""
        self._user_agent: str = user_agent
        self._logger = logger
        self._session: ClientSession = session or self._new_session()

    def _new_session(self) -> ClientSession:
        return ClientSession(
            timeout=ClientTimeout(total=DEFAULT_TIMEOUT),
            raise_for_status=False,
        )

    async def _request(
        self, method: str, url: str, **kwargs: Any
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

        kwargs["headers"]["appkey"] = self._application_key

        if self._access_token != "":
            kwargs["headers"]["Authorization"] = f"Bearer {self._access_token}"

        if use_running_session := self._session and not self._session.closed:
            session = self._session
        else:
            session = self._new_session()

        try:
            async with session.request(method, f"{API_HOST}/{url}", **kwargs) as resp:
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
            "appkey": self._application_key,
            "scope": "server",
            "username": username,
            "password": password,
        }
        headers = {
            "User-Agent": self._user_agent,
            "Authorization": f"Basic {self._application_auth}",
        }
        resp = await self._request(
            "post", "auth/oauth/token?grant_type=password", data=FormData(data), headers=headers
        )
        if resp is None or resp["code"] != 200 or resp["access_token"] is None:
            raise InvalidCredentialsError

        return Token(
            app_id=self._application_key,
            username=username,
            password=password,
            access_token=resp["access_token"],
            uid=resp["user_id"],
        )

    async def get_device_list(self) -> list[Device]:
        """Get device list."""
        resp = await self._request(
            "get",
            f"app/device/getBindList?appKey={self._application_key}&version=1.0",
        )
        if resp.get("code") != 200:
            raise RequestError
        return [
            Device(
                id=d.get("did"),
                mac=d.get("mac"),
                product_key=d.get("productKey"),
                product_id=d.get("productId"),
                product_name=d.get("productName"),
                product_verbose_name=d.get("verboseName"),
                is_online=d.get("isOnline") == 1,
                is_manager=d.get("isManger") == 1,
                group_id=d.get("groupId"),
                sno=d.get("sno"),
                create_time=d.get("ctime"),
                last_offline_time=d.get("lastOfflineTime"),
                model_alias=d["modelInfo"]["aliasName"],
                model=d["modelInfo"]["model"],
                serial_number=d["serialNumber"],
                services_count=d["servicesCount"],
            )
            for d in resp["data"][0]["allBindList"]
        ]

    async def control_device(self, device_id: str, attr_name: str, value: Any):
        """Control device."""
        resp = await self._request(
            "post",
            f"app/device/control/{device_id}",
            json={
                "appKey": self._application_key,
                "data": {
                    "attrs": {
                        f"{attr_name}": value
                    }
                },
                "version": "1.0"
            }
        )
        if resp.get("code") != 200:
            raise RequestError
        