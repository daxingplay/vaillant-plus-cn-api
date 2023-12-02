"""Configurations for test cases."""

import json
from aiohttp import web, WSMsgType
from aiohttp.test_utils import BaseTestServer
from aiohttp.helpers import sentinel
from pytest_asyncio import fixture as asyncio_fixture

from typing import (
    TYPE_CHECKING,
    Any,
    Optional,
    Union,
    Callable,
    Awaitable,
)

TEST_USERNAME = "daxingplay"
TEST_PASSWORD = "password"


class FakeWebsocketServer(BaseTestServer):
    """Define a fake websocket server for test."""

    def __init__(
        self,
        loop,
        *,
        scheme: Union[str, object] = sentinel,
        host: str = "127.0.0.1",
        port: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        self._loop = loop
        self._message_handler: Callable[[
            dict[str, Any], web.WebSocketResponse], Awaitable] | None = None
        super().__init__(scheme=scheme, host=host, port=port, loop=loop, **kwargs)

    async def _make_runner(self, **kwargs):
        app = web.Application()
        app.add_routes([web.get('/monitor/ws/app', self._websocket_handler)])
        return web.AppRunner(app=app, **kwargs)

    async def _websocket_handler(self, request):

        ws = web.WebSocketResponse()
        await ws.prepare(request)

        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                data = json.loads(msg.data)
                if self._message_handler is not None:
                    await self._message_handler(data, ws)
                else:
                    print('no message handler defined')
            elif msg.type == WSMsgType.ERROR:
                print('ws connection closed with exception %s' %
                      ws.exception())

        print('websocket connection closed')

        return ws

    def add_handler(self, handler: Callable[[dict[str, Any], web.WebSocketResponse], Awaitable]):
        self._message_handler = handler


@asyncio_fixture(scope="function")
async def websocket_server(event_loop):
    async with FakeWebsocketServer(loop=event_loop) as server:
        yield server
