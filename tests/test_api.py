"""Define tests for the API."""

import pytest
import aiohttp
import json
from aresponses import ResponsesMockServer

from vaillant_plus_cn_api import VaillantApiClient
from vaillant_plus_cn_api.const import HOST_APP, HOST_API
from vaillant_plus_cn_api.errors import InvalidAuthError, RequestError
from .common import TEST_USERNAME, TEST_PASSWORD


@pytest.mark.asyncio
async def test_api_request_error(aresponses: ResponsesMockServer) -> None:
    """Test the API client raising an exception upon HTTP error.

    Args:
        aresponses: An aresponses server.
    """
    aresponses.add(
        HOST_APP.removeprefix("https://"),
        "/app/user/login",
        "post",
        aresponses.Response(
            text="",
            content_type="application/json",
            status=500,
        ),
    )

    async with aiohttp.ClientSession() as session:
        api = VaillantApiClient(session=session)

        with pytest.raises(RequestError):
            await api.login(TEST_USERNAME, TEST_PASSWORD)


@pytest.mark.asyncio
async def test_api_invalid_auth_error(aresponses: ResponsesMockServer) -> None:
    """Test the API client raising an exception when auth failed.

    Args:
        aresponses: An aresponses server.
    """
    aresponses.add(
        HOST_APP.removeprefix("https://"),
        "/app/user/login",
        "post",
        aresponses.Response(
            text=json.dumps({
                "code": "500"
            }),
            content_type="application/json",
            status=200,
        ),
    )

    async with aiohttp.ClientSession() as session:
        api = VaillantApiClient(session=session)

        with pytest.raises(InvalidAuthError):
            await api.login(TEST_USERNAME, TEST_PASSWORD)


@pytest.mark.asyncio
async def test_api_login(aresponses: ResponsesMockServer) -> None:
    """Test the API client login process.

    Args:
        aresponses: An aresponses server.
    """
    aresponses.add(
        HOST_APP.removeprefix("https://"),
        "/app/user/login",
        "post",
        aresponses.Response(
            text=json.dumps({
                "code": "200",
                "data": {
                    "token": "123",
                    "uid": "1"
                }
            }),
            content_type="application/json",
            status=200,
        ),
    )

    async with aiohttp.ClientSession() as session:
        api = VaillantApiClient(session=session)

        token = await api.login(TEST_USERNAME, TEST_PASSWORD)
        assert token.token == "123"
        assert token.uid == "1"
        assert token.username == TEST_USERNAME
        assert token.password == TEST_PASSWORD


@pytest.mark.asyncio
async def test_api_get_device_list_error(aresponses: ResponsesMockServer) -> None:
    """Test the API client raise an auth error when using an invalid token to get device list.

    Args:
        aresponses: An aresponses server.
    """
    aresponses.add(
        HOST_API.removeprefix("https://"),
        "/app/bindings",
        "get",
        aresponses.Response(
            text=json.dumps({
                "error_message": "token invalid!",
                "error_code": 9004,
                "detail_message": None,
            }),
            content_type="application/json",
            status=400,
        ),
    )

    async with aiohttp.ClientSession() as session:
        api = VaillantApiClient(session=session)

        with pytest.raises(InvalidAuthError):
            await api.get_device_list("1")


@pytest.mark.asyncio
async def test_api_get_device_list(aresponses: ResponsesMockServer) -> None:
    """Test the API client get device list method.

    Args:
        aresponses: An aresponses server.
    """
    aresponses.add(
        HOST_API.removeprefix("https://"),
        "/app/bindings",
        "get",
        aresponses.Response(
            text=json.dumps({
                "devices": [
                    {
                        "remark": "",
                        "protoc": 3,
                        "wss_port": 8,
                        "ws_port": 9,
                        "did": "1",
                        "port_s": 10,
                        "is_disabled": False,
                        "wifi_soft_version": "wsv1",
                        "product_key": "abcdefg",
                        "port": 11,
                        "mac": "12345678abcd",
                        "role": "owner",
                        "dev_alias": "",
                        "is_sandbox": True,
                        "is_online": True,
                        "host": "test_host",
                        "type": "normal",
                        "product_name": "vSmartPro"
                    }
                ]
            }),
            content_type="application/json",
            status=200,
        ),
    )

    async with aiohttp.ClientSession() as session:
        api = VaillantApiClient(session=session)

        devices = await api.get_device_list("1")
        assert len(devices) == 1
        assert devices[0].id == "1"
        assert devices[0].mac == "12345678abcd"
        assert devices[0].product_key == "abcdefg"
        assert devices[0].host == "test_host"
        assert devices[0].wss_port == 8
        assert devices[0].wifi_soft_version == "wsv1"
        assert devices[0].wifi_hard_version == ""
        assert devices[0].mcu_soft_version == ""
        assert devices[0].mcu_hard_version == ""
        assert devices[0].is_online == True


@pytest.mark.asyncio
async def test_api_get_device_info(aresponses: ResponsesMockServer) -> None:
    """Test the API client get device info method.

    Args:
        aresponses: An aresponses server.
    """
    aresponses.add(
        HOST_APP.removeprefix("https://"),
        "/app/device/sn/status",
        "get",
        aresponses.Response(
            text=json.dumps({
                "code": "200",
                "data": {
                    "gizDid": "1",
                    "mac": "12345678abcd",
                    "model": "model_test",
                    "serialNumber": "2",
                    "sno": "3",
                    "status": 1
                },
                "display": None,
                "message": "本次请求成功!"
            }),
            content_type="application/json",
            status=200,
        ),
    )

    async with aiohttp.ClientSession() as session:
        api = VaillantApiClient(session=session)

        device = await api.get_device_info("1", "12345678abcd")
        assert device.get("sno") == "3"
        assert device.get("mac") == "12345678abcd"
        assert device.get("device_id") == "1"
        assert device.get("serial_number") == "2"
        assert device.get("model") == "model_test"
        assert device.get("status_code") == 1


@pytest.mark.asyncio
async def test_api_get_device_info_auth_error(aresponses: ResponsesMockServer) -> None:
    """Test the API client raise an auth error when getting device info.

    Args:
        aresponses: An aresponses server.
    """
    aresponses.add(
        HOST_APP.removeprefix("https://"),
        "/app/device/sn/status",
        "get",
        aresponses.Response(
            text=json.dumps({
                "code": "505",
                "message": "未登录",
                "data": None,
                "display": None
            }),
            content_type="application/json",
            status=200,
        ),
    )

    async with aiohttp.ClientSession() as session:
        api = VaillantApiClient(session=session)

        with pytest.raises(InvalidAuthError):
            await api.get_device_info("1", "12345678abcd")
