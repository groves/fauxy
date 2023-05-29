from asyncio import iscoroutine
import io
import json
import os
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Optional,
    Tuple,
    TypeAlias,
)
from anyio import Path
from starlette.background import BackgroundTask, BackgroundTasks
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from httpx import AsyncClient, Headers
from hashlib import blake2b
from fauxy.library import Library, Recording


HeaderProcessor: TypeAlias = Callable[[Headers], None]
ResponseProcessor: TypeAlias = Callable[[Response], None]


class Recorder:
    def __init__(
        self,
        rec: Recording,
        key: bytes,
        header_processors: list[HeaderProcessor],
        response_processors: list[ResponseProcessor],
    ):
        self.rec = rec
        self.key = key
        self.header_processors = header_processors
        self.response_processors = response_processors

    async def tee(self, iter: AsyncIterator[bytes]):
        self._content = io.BytesIO() if self.response_processors else None
        appender = self._content.write if self._content else lambda x: None
        async with await self.rec.response.open(mode="wb") as f:
            async for b in iter:
                await f.write(b)
                appender(b)
                yield b

    async def save(self, response):
        for processor in self.header_processors:
            processor(response.headers)
        meta = {
            "status": response.status_code,
            "headers": dict(response.headers.items()),
        }
        async with await self.rec.meta.open(mode="wb") as f:
            await f.write(json.dumps(meta, indent=2).encode())

        async with await self.rec.key.open(mode="wb") as f:
            await f.write(self.key)


def strip_headers(*names) -> HeaderProcessor:
    def stripper(headers: Headers):
        for name in names:
            try:
                del headers[name]
            except KeyError:
                # We're only trying to remove the header, we don't care if it's already not there
                pass

    return stripper


class RecordingProxy:
    def __init__(
        self,
        base_url: str,
        library: Library,
        header_processors: Optional[list[HeaderProcessor]] = None,
        response_processors: Optional[list[Callable[[Response], None]]] = None,
        disable_default_header_processors: Optional[bool] = False,
    ):
        self.client = AsyncClient(base_url=base_url)
        self.library = library
        self.response_processors = response_processors if response_processors else []
        self.header_processors = (
            [strip_headers("date")] if not disable_default_header_processors else []
        )
        self.header_processors.extend(header_processors if header_processors else [])

    async def record(self, in_req: Request):
        headers = {**in_req.headers}
        # Delete any incoming host header so httpx will fill in the destination host in build_request
        if "host" in headers:
            del headers["host"]
        # Build a request for the same method and path
        proxy_req = self.client.build_request(
            in_req.method,
            in_req.url.path,
            headers=headers,
            params=in_req.query_params,
            content=in_req.stream(),
        )

        recording, key_bytes = await self.library.create(in_req)
        rec = Recorder(
            recording, key_bytes, self.header_processors, self.response_processors
        )

        # Send the new request and get back the headers but leave the body for streaming
        resp = await self.client.send(proxy_req, stream=True)

        # Return a response that streams the body from the request into it, sending back the status
        # code and headers from the upstream response
        return StreamingResponse(
            rec.tee(resp.aiter_bytes()),
            resp.status_code,
            resp.headers,
            # Close the upstream reader once we're done streaming the response
            background=BackgroundTasks(
                [BackgroundTask(resp.aclose), BackgroundTask(rec.save, resp)]
            ),
        )
