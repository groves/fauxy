import io
import json
import os
from typing import (
    Any,
    AsyncIterable,
    AsyncIterator,
    Callable,
    Optional,
    Tuple,
    TypeAlias,
)
from anyio import Path
from starlette.applications import Starlette
from starlette.background import BackgroundTask, BackgroundTasks
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Mount, Route
from httpx import AsyncClient, Headers
from hashlib import blake2b


client = AsyncClient(base_url="https://v2.jokeapi.dev")

JSON: TypeAlias = dict[str, "JSON"] | list["JSON"] | str | int | float | bool | None


class Recording:
    def __init__(self, rec_dir: Path, key: bytes):
        self.rec_dir = rec_dir
        self.key = key

    async def tee(self, iter: AsyncIterator[bytes]):
        rec_content = self.rec_dir / "response.content"
        async with await rec_content.open(mode="wb") as f:
            async for b in iter:
                await f.write(b)
                yield b

    async def save(self, response):
        rec_meta = self.rec_dir / "meta.json"
        meta = {
            "status": response.status_code,
            "headers": dict(response.headers.items()),
        }
        async with await rec_meta.open(mode="wb") as f:
            await f.write(json.dumps(meta, indent=2).encode())

        async with await (self.rec_dir / "key.json").open(mode="wb") as f:
            await f.write(self.key)


KeyMaker: TypeAlias = Callable[[Request], JSON]


def make_key_hash(key: JSON) -> Tuple[bytes, str]:
    key_bytes = json.dumps(key, indent=2).encode()

    hash = blake2b(digest_size=4)
    hash.update(key_bytes)
    return key_bytes, hash.hexdigest()


class Recorder:
    def __init__(self, key_maker: KeyMaker, base_dir: Optional[Path] = None):
        self.base_dir = base_dir
        self.key_maker = key_maker

    async def create(self, req: Request) -> Recording:
        if self.base_dir is None:
            self.base_dir = await Path.cwd()
        key = self.key_maker(req)
        key_bytes, hash = make_key_hash(key)
        rec_dir = self.base_dir / req.url.path[1:] / hash
        await rec_dir.mkdir(parents=True, exist_ok=True)
        return Recording(rec_dir, key_bytes)


def path_key(req: Request) -> JSON:
    return {"path": req.url.path}


def path_and_query_key(req: Request) -> JSON:
    return {"path": req.url.path, "safe": "safe-mode" in req.query_params}


recorder = Recorder(path_and_query_key)


async def record(in_req: Request):
    headers = {**in_req.headers}
    # Delete the incoming host header so httpx will fill in the destination host in build_request
    del headers["host"]
    # Build a request for the same method and path
    proxy_req = client.build_request(
        in_req.method,
        in_req.url.path,
        headers=headers,
        params=in_req.query_params,
    )

    rec = await recorder.create(in_req)

    # Send the new request and get back the headers but leave the body for streaming
    resp = await client.send(proxy_req, stream=True)

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


app = Starlette(
    debug=True,
    routes=[
        Route("/{path:path}", record),
    ],
)
