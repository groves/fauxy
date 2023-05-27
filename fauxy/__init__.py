from typing import (
    Any,
    AsyncIterator,
    Callable,
    Optional,
    Tuple,
    TypeAlias,
)

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
