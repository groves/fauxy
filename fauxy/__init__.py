import asyncio
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Optional,
    Tuple,
    TypeAlias,
    Union,
)
import anyio

from uvicorn import Config
from uvicorn.server import Server
from asgiref.typing import ASGIApplication

from starlette.requests import Request
from starlette.responses import Response

JSON: TypeAlias = dict[str, "JSON"] | list["JSON"] | str | int | float | bool | None
KeyMaker: TypeAlias = Callable[[Request], JSON]

from fauxy.record import Recorder
from fauxy.replay import Library


class ProxyOnce:
    def __init__(self, recorder: Recorder, library: Library):
        self.recorder = recorder
        self.library = library

    async def serve(self, req: Request) -> Response:
        if found := await self.library.find(req):
            return await self.library.serve(found)
        return await self.recorder.record(req)


async def serve(app: Union[str, ASGIApplication, Callable]):
    server = Server(Config(app, port=0))
    with anyio.from_thread.start_blocking_portal() as bp:
        bp.start_task_soon(server.serve)
        while not server.started:
            await asyncio.sleep(0.1)

        port = server.servers[0].sockets[0].getsockname()[1]
        yield port
        server.should_exit = True
