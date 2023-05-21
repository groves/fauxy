import json
from anyio import Path
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route


async def replay(in_req: Request):
    rec_dir = (await Path.cwd()) / in_req.url.path[1:]
    if not await rec_dir.exists():
        return Response(f"No recording at {rec_dir}", status_code=424)
    rec_meta = rec_dir / "meta.json"
    rec_content = rec_dir / "content"
    if not await rec_meta.exists():
        return Response(f"No meta.json in {rec_dir}", status_code=424)
    if not await rec_content.exists():
        return Response(f"No content in {rec_dir}", status_code=424)

    meta = json.loads(await (await rec_meta.open("r")).read())
    return StreamingResponse(
        await rec_content.open("rb"), meta["status"], meta["headers"]
    )


app = Starlette(
    debug=True,
    routes=[
        Route("/{path:path}", replay),
    ],
)
