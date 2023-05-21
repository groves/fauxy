import json
import os
from typing import AsyncIterable, AsyncIterator
from anyio import Path
from starlette.applications import Starlette
from starlette.background import BackgroundTask, BackgroundTasks
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Mount, Route
from httpx import AsyncClient, Headers


client = AsyncClient(base_url="https://v2.jokeapi.dev")


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

    rec_dir = (await Path.cwd()) / in_req.url.path[1:]
    await rec_dir.mkdir(parents=True, exist_ok=True)
    rec_meta = rec_dir / "meta.json"
    rec_content = rec_dir / "content"

    # Send the new request and get back the headers but leave the body for streaming
    resp = await client.send(proxy_req, stream=True)

    async def meta_recorder():
        meta = {"status": resp.status_code, "headers": dict(resp.headers.items())}
        async with await rec_meta.open(mode="wb") as f:
            await f.write(json.dumps(meta).encode())

    async def tee(iter: AsyncIterator[bytes]):
        async with await rec_content.open(mode="wb") as f:
            async for b in iter:
                await f.write(b)
                yield b

    # Return a response that streams the body from the request into it, sending back the status
    # code and headers from the upstream response
    return StreamingResponse(
        tee(resp.aiter_bytes()),
        resp.status_code,
        resp.headers,
        # Close the upstream reader once we're done streaming the response
        background=BackgroundTasks(
            [BackgroundTask(task) for task in [resp.aclose, meta_recorder]]
        ),
    )


app = Starlette(
    debug=True,
    routes=[
        Route("/{path:path}", record),
    ],
)
