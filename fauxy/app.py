import json
from anyio import Path
from typing import Awaitable, Callable, Optional
from fauxy.library import KeyMaker, Library, Recording
from fauxy.record import HeaderProcessor, Recorder, RecordingProxy
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, Response, StreamingResponse
from starlette.routing import Route


async def _create_response(rec: Recording) -> Response:
    meta = json.loads(await (await rec.meta.open("r")).read())
    return FileResponse(rec.response, meta["status"], meta["headers"])


def create_proxy_route(
    handler: Callable[[Request], Awaitable[Response]], path: str = "/{_:path}"
) -> Route:
    # Proxy all paths, ignoring the filled in path param
    r = Route(path, handler)

    # Allow matching on any method
    # Route fills in methods if we pass it None, so we set it to None to match all methods after init
    # TODO let methods be specified.
    # We'll likely want to include the matched method in the key if it's specified
    r.methods = None
    return r


def replay(library_dir: Path, key_maker: KeyMaker) -> Route:
    library = Library(key_maker=key_maker, base_dir=library_dir)

    async def replay(req: Request) -> Response:
        if found := await library.find(req):
            return await _create_response(found)
        return Response("No replay found for ", status_code=424)

    return create_proxy_route(replay)


def proxy(
    base_url: str,
    library_dir: Path | str,
    key_maker: KeyMaker,
    path: str = "/{_:path}",
    header_processors: list[HeaderProcessor] | None = None,
    response_processors: list[Callable[[Response], None]] | None = None,
    disable_default_header_processors: bool | None = False,
) -> Route:
    library = Library(key_maker=key_maker, base_dir=library_dir)

    proxy = RecordingProxy(
        base_url=base_url,
        library=library,
        header_processors=header_processors,
        response_processors=response_processors,
        disable_default_header_processors=disable_default_header_processors,
    )

    async def proxy_once(req: Request) -> Response:
        if found := await library.find(req):
            resp = await _create_response(found)
            return resp
        return await proxy.record(req)

    return create_proxy_route(proxy_once, path)


def app(routes: list[Route]) -> Starlette:
    return Starlette(debug=True, routes=routes)
