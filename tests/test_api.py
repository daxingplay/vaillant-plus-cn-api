"""Define tests for the API."""

import pytest
import aiohttp
import json
import asyncio
from aresponses import ResponsesMockServer

from vaillant_plus_cn_api import VaillantApiClient
from vaillant_plus_cn_api.const import API_HOST
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
        API_HOST.removeprefix("https://"),
        "/auth/oauth/token",
        "post",
        aresponses.Response(
            text=json.dumps({
                "access_token": "at1",
                "active": True,
                "client_id": "app-w",
                "code": 200,
                "expires_in": 2591999,
                "giz_refresh_token": "giz_r_t1",
                "giz_token": "giz_t1",
                "giz_uid": "giz_u1",
                "license": "made by iot",
                "platform": 0,
                "refresh_token": "r_t1",
                "scope": "server",
                "token_type": "bearer",
                "user_id": "1234",
                "username": "u1"
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
        API_HOST.removeprefix("https://"),
        "/auth/oauth/token",
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
                "access_token": "at1",
                "active": True,
                "client_id": "app-w",
                "code": 200,
                "expires_in": 2591999,
                "giz_refresh_token": "giz_r_t1",
                "giz_token": "giz_t1",
                "giz_uid": "giz_u1",
                "license": "made by iot",
                "platform": 0,
                "refresh_token": "r_t1",
                "scope": "server",
                "token_type": "bearer",
                "user_id": "1234",
                "username": "u1"
            }),
            content_type="application/json",
            status=200,
        )

    aresponses.add(
        API_HOST.removeprefix("https://"),
        "/auth/oauth/token",
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
        API_HOST.removeprefix("https://"),
        "/auth/oauth/token",
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
        API_HOST.removeprefix("https://"),
        "/auth/oauth/token",
        "post",
        aresponses.Response(
            text=json.dumps({
                "access_token": "123",
                "active": True,
                "client_id": "app-w",
                "code": 200,
                "expires_in": 2591999,
                "giz_refresh_token": "giz_r_t1",
                "giz_token": "giz_t1",
                "giz_uid": "giz_u1",
                "license": "made by iot",
                "platform": 0,
                "refresh_token": "r_t1",
                "scope": "server",
                "token_type": "bearer",
                "user_id": "1",
                "username": "u1"
            }),
            content_type="application/json",
            status=200,
        ),
    )

    async with aiohttp.ClientSession() as session:
        api = VaillantApiClient(session=session)

        token = await api.login(TEST_USERNAME, TEST_PASSWORD)
        assert token.access_token == "123"
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
        API_HOST.removeprefix("https://"),
        "/app/device/getBindList",
        "get",
        aresponses.Response(
            text=json.dumps({
                "code": 9006,
                "msg": "token 过期",
                "data": "Invalid token: 123"
            }),
            content_type="application/json",
            status=424,
        ),
    )

    async with aiohttp.ClientSession() as session:
        api = VaillantApiClient(session=session)

        with pytest.raises(InvalidAuthError):
            await api.get_device_list()

    aresponses.assert_plan_strictly_followed()

@pytest.mark.asyncio
async def test_api_get_device_list_request_error(aresponses: ResponsesMockServer) -> None:
    """Test the API client raise an auth error when using an invalid token to get device list.

    Args:
        aresponses: An aresponses server.
    """
    aresponses.add(
        API_HOST.removeprefix("https://"),
        "/app/device/getBindList",
        "get",
        aresponses.Response(
            text=json.dumps({
                "code": 9006,
                "msg": "token 过期",
                "data": "Invalid token: 123"
            }),
            content_type="application/json",
            status=200,
        ),
    )

    async with aiohttp.ClientSession() as session:
        api = VaillantApiClient(session=session)

        with pytest.raises(RequestError):
            await api.get_device_list()

    aresponses.assert_plan_strictly_followed()

@pytest.mark.asyncio
async def test_api_get_device_list(aresponses: ResponsesMockServer) -> None:
    """Test the API client get device list method.

    Args:
        aresponses: An aresponses server.
    """
    aresponses.add(
        API_HOST.removeprefix("https://"),
        "/app/device/getBindList",
        "get",
        aresponses.Response(
            text=json.dumps({
                "code": 200,
                "data": [
                    {
                        "allBindList": [
                            {
                                "ctime": "1900-01-01 00:00:00",
                                "devAlias": "威精灵",
                                "devLabel": None,
                                "deviceSn": None,
                                "did": "1",
                                "homeId": 2,
                                "homeName": "家",
                                "isManger": 1,
                                "isOnline": 1,
                                "lastOfflineTime": "2023-12-31 23:59:59",
                                "mac": "12345678abcd",
                                "modelInfo": {
                                    "aliasName": "两用炉",
                                    "model": "model1"
                                },
                                "productId": 3,
                                "productKey": "abcdefg",
                                "productName": "威精灵",
                                "roomId": 5,
                                "roomName": "home",
                                "serialNumber": "6",
                                "servicesCount": 7,
                                "sno": "8",
                                "verboseName": "威能温控器"
                            }
                        ],
                        "deviceCount": 1,
                        "groupCount": 1,
                        "groupList": [
                            {
                                "bindList": [
                                    {
                                        "ctime": "1900-01-01 00:00:00",
                                        "devAlias": "威精灵",
                                        "devLabel": None,
                                        "deviceSn": None,
                                        "did": "1",
                                        "homeId": 2,
                                        "homeName": "家",
                                        "isManger": 1,
                                        "isOnline": 1,
                                        "lastOfflineTime": "2023-12-31 23:59:59",
                                        "mac": "12345678abcd",
                                        "modelInfo": {
                                            "aliasName": "两用炉",
                                            "model": "model1"
                                        },
                                        "productId": 3,
                                        "productKey": "abcdefg",
                                        "productName": "威精灵",
                                        "roomId": 5,
                                        "roomName": "home",
                                        "serialNumber": "6",
                                        "servicesCount": 7,
                                        "sno": "8",
                                        "verboseName": "威能温控器"
                                    }
                                ],
                                "id": 8,
                                "name": "家"
                            }
                        ],
                        "id": 9,
                        "location": "未设置地理位置",
                        "locationId": "",
                        "name": "家",
                        "shareBindList": []
                    }
                ],
                "display": None,
                "msg": "本次请求成功!"
            }
),
            content_type="text/html",
            status=200,
        ),
    )

    async with aiohttp.ClientSession() as session:
        api = VaillantApiClient(session=session)

        devices = await api.get_device_list()
        assert len(devices) == 1
        assert devices[0].id == "1"
        assert devices[0].mac == "12345678abcd"
        assert devices[0].product_key == "abcdefg"
        assert devices[0].is_online == True

    aresponses.assert_plan_strictly_followed()


@pytest.mark.asyncio
async def test_api_control_device(aresponses: ResponsesMockServer) -> None:
    """Test the API client control device method.

    Args:
        aresponses: An aresponses server.
    """
    aresponses.add(
        API_HOST.removeprefix("https://"),
        "/app/device/control/1",
        "post",
        aresponses.Response(
            text=json.dumps({
                "code": 200,
                "data": None,
                "display": None,
                "msg": "本次请求成功!"
            }),
            content_type="application/json",
            status=200,
        ),
    )

    async with aiohttp.ClientSession() as session:
        api = VaillantApiClient(session=session)

        await api.control_device("1", "DHW_setpoint", 45.5)

    aresponses.assert_plan_strictly_followed()


@pytest.mark.asyncio
async def test_api_control_device_auth_error(aresponses: ResponsesMockServer) -> None:
    """Test the API client raise an auth error when controlling the device.

    Args:
        aresponses: An aresponses server.
    """
    aresponses.add(
        API_HOST.removeprefix("https://"),
        "/app/device/control/1",
        "post",
        aresponses.Response(
            text=json.dumps({
                "code": 9006,
                "msg": "token 过期",
                "data": "Invalid token: 123"
            }),
            content_type="application/json",
            status=424,
        ),
    )

    async with aiohttp.ClientSession() as session:
        api = VaillantApiClient(session=session)

        with pytest.raises(InvalidAuthError):
            await api.control_device("1", "DHW_setpoint", 45.5)
    
    aresponses.assert_plan_strictly_followed()

@pytest.mark.asyncio
async def test_api_get_device_info_request_error(aresponses: ResponsesMockServer) -> None:
    """Test the API client raise an auth error when getting device info.

    Args:
        aresponses: An aresponses server.
    """
    aresponses.add(
        API_HOST.removeprefix("https://"),
        "/app/device/control/1",
        "post",
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
            await api.control_device("1", "DHW_setpoint", 45.5)

    aresponses.assert_plan_strictly_followed()

@pytest.mark.asyncio
async def test_api_request_with_auth_header(aresponses: ResponsesMockServer) -> None:
    """Test the API client request process with proper authorization header.

    Args:
        aresponses: An aresponses server.
    """
    aresponses.add(
        API_HOST.removeprefix("https://"),
        "/auth/oauth/token",
        "post",
        aresponses.Response(
            text=json.dumps({
                "access_token": "123",
                "active": True,
                "client_id": "app-w",
                "code": 200,
                "expires_in": 2591999,
                "giz_refresh_token": "giz_r_t1",
                "giz_token": "giz_t1",
                "giz_uid": "giz_u1",
                "license": "made by iot",
                "platform": 0,
                "refresh_token": "r_t1",
                "scope": "server",
                "token_type": "bearer",
                "user_id": "1",
                "username": "u1"
            }),
            content_type="application/json",
            status=200,
        ),
    )

    aresponses.add(
        API_HOST.removeprefix("https://"),
        "/app/device/control/1",
        "post",
        aresponses.Response(
            text=json.dumps({
                "code": 200,
                "data": None,
                "display": None,
                "msg": "本次请求成功!"
            }),
            content_type="application/json",
            status=200,
        ),
    )

    async with aiohttp.ClientSession() as session:
        api = VaillantApiClient(session=session)

        token = await api.login(TEST_USERNAME, TEST_PASSWORD)
        assert token.access_token == "123"
        assert token.uid == "1"
        assert token.username == TEST_USERNAME
        assert token.password == TEST_PASSWORD
        await api.control_device("1", "Test", 0)

    aresponses.assert_plan_strictly_followed()