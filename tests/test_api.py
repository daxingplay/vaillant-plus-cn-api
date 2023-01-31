"""Define tests for the API."""

import pytest
import aiohttp
import json
import asyncio
from aresponses import ResponsesMockServer

from vaillant_plus_cn_api import VaillantApiClient
from vaillant_plus_cn_api.const import HOST_APP, HOST_API
from vaillant_plus_cn_api.errors import InvalidAuthError, RequestError, InvalidCredentialsError
from .conftest import TEST_USERNAME, TEST_PASSWORD

@pytest.mark.asyncio
async def test_api_session() -> None:
    """Test the API client automatically create a new session when session arg is None.
    """
    api = VaillantApiClient()
    assert api._session is not None

@pytest.mark.asyncio
async def test_api_request_session(aresponses: ResponsesMockServer) -> None:
    """Test the API client automatically create a new session if old session closed.

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

    api = VaillantApiClient()
    await api._session.close()
    await api.login(TEST_USERNAME, TEST_PASSWORD)
    assert api._session is not None
    assert api._session.closed is True
    aresponses.assert_plan_strictly_followed()

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
    
    aresponses.assert_plan_strictly_followed()

@pytest.mark.asyncio
async def test_api_request_timeout_error(aresponses: ResponsesMockServer) -> None:
    """Test the API client raising an exception upon client error.
       Then the client should close session if the session was created during request.
       (not use_running_session)
    Args:
        aresponses: An aresponses server.
    """

    async def response_handler(request):
        await asyncio.sleep(0.1)
        return aresponses.Response(
            text=json.dumps({
                "code": "200",
                "data": {
                    "token": "123",
                    "uid": "1"
                }
            }),
            content_type="application/json",
            status=200,
        )

    aresponses.add(
        HOST_APP.removeprefix("https://"),
        "/app/user/login",
        "post",
        response_handler,
    )

    api = VaillantApiClient()
    await api._session.close()

    def _new_session() -> aiohttp.ClientSession:
        return aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(0.05),
            raise_for_status=False,
        )
    api._new_session = _new_session

    with pytest.raises(asyncio.TimeoutError):
        await api.login(TEST_USERNAME, TEST_PASSWORD)
    
    assert api._session.closed
    aresponses.assert_plan_strictly_followed()

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

        with pytest.raises(InvalidCredentialsError):
            await api.login(TEST_USERNAME, TEST_PASSWORD)

    aresponses.assert_plan_strictly_followed()


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

    aresponses.assert_plan_strictly_followed()


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

    aresponses.assert_plan_strictly_followed()

@pytest.mark.asyncio
async def test_api_get_device_list_request_error(aresponses: ResponsesMockServer) -> None:
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
            status=200,
        ),
    )

    async with aiohttp.ClientSession() as session:
        api = VaillantApiClient(session=session)

        with pytest.raises(RequestError):
            await api.get_device_list("1")

    aresponses.assert_plan_strictly_followed()

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
            content_type="text/html",
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
        assert devices[0].ws_port == 9
        assert devices[0].wifi_soft_version == "wsv1"
        assert devices[0].wifi_hard_version == ""
        assert devices[0].mcu_soft_version == ""
        assert devices[0].mcu_hard_version == ""
        assert devices[0].is_online == True

    aresponses.assert_plan_strictly_followed()


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

    aresponses.assert_plan_strictly_followed()


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
    
    aresponses.assert_plan_strictly_followed()

@pytest.mark.asyncio
async def test_api_get_device_info_request_error(aresponses: ResponsesMockServer) -> None:
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
                "code": "11111111",
                "message": "Unknown code",
                "data": None,
                "display": None
            }),
            content_type="application/json",
            status=200,
        ),
    )

    async with aiohttp.ClientSession() as session:
        api = VaillantApiClient(session=session)

        with pytest.raises(RequestError):
            await api.get_device_info("1", "12345678abcd")

    aresponses.assert_plan_strictly_followed()