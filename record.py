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


JSON: TypeAlias = dict[str, "JSON"] | list["JSON"] | str | int | float | bool | None


HeaderProcessor: TypeAlias = Callable[[Headers], None]
KeyMaker: TypeAlias = Callable[[Request], JSON]
ResponseProcessor: TypeAlias = Callable[[Response], None]


class Recording:
    def __init__(
        self,
        rec_dir: Path,
        key: bytes,
        header_processors: list[HeaderProcessor],
        response_processors: list[ResponseProcessor],
    ):
        self.rec_dir = rec_dir
        self.key = key
        self.header_processors = header_processors
        self.response_processors = response_processors

    async def tee(self, iter: AsyncIterator[bytes]):
        rec_content = self.rec_dir / "response.content"
        self._content = io.BytesIO() if self.response_processors else None
        appender = self._content.write if self._content else lambda x: None
        async with await rec_content.open(mode="wb") as f:
            async for b in iter:
                await f.write(b)
                appender(b)
                yield b

    async def save(self, response):
        for processor in self.header_processors:
            processor(response.headers)
        rec_meta = self.rec_dir / "meta.json"
        meta = {
            "status": response.status_code,
            "headers": dict(response.headers.items()),
        }
        async with await rec_meta.open(mode="wb") as f:
            await f.write(json.dumps(meta, indent=2).encode())

        async with await (self.rec_dir / "key.json").open(mode="wb") as f:
            await f.write(self.key)


def make_key_hash(key: JSON) -> Tuple[bytes, str]:
    key_bytes = json.dumps(key, indent=2).encode()

    hash = blake2b(digest_size=4)
    hash.update(key_bytes)
    return key_bytes, hash.hexdigest()


def strip_headers(*names) -> HeaderProcessor:
    def stripper(headers):
        for name in names:
            del headers[name]

    return stripper


class Recorder:
    def __init__(
        self,
        base_url: str,
        key_maker: KeyMaker,
        header_processors: Optional[list[HeaderProcessor]] = None,
        response_processors: Optional[list[Callable[[Response], None]]] = None,
        base_dir: Optional[Path] = None,
        disable_default_header_processors: Optional[bool] = False,
    ):
        self.client = AsyncClient(base_url=base_url)
        self.base_dir = base_dir
        self.key_maker = key_maker
        self.response_processors = response_processors if response_processors else []
        self.header_processors = (
            [strip_headers("date")] if not disable_default_header_processors else []
        )
        self.header_processors.extend(header_processors if header_processors else [])

    async def create(self, req: Request) -> Recording:
        if self.base_dir is None:
            self.base_dir = await Path.cwd()
        key = self.key_maker(req)
        key_bytes, hash = make_key_hash(key)
        rec_dir = self.base_dir / req.url.path[1:] / hash
        await rec_dir.mkdir(parents=True, exist_ok=True)
        return Recording(
            rec_dir, key_bytes, self.header_processors, self.response_processors
        )

    async def record(self, in_req: Request):
        headers = {**in_req.headers}
        # Delete the incoming host header so httpx will fill in the destination host in build_request
        del headers["host"]
        # Build a request for the same method and path
        proxy_req = self.client.build_request(
            in_req.method,
            in_req.url.path,
            headers=headers,
            params=in_req.query_params,
        )

        rec = await self.create(in_req)

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
