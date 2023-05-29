import json
from anyio import Path
from typing import Awaitable, Callable, Optional
from fauxy.library import KeyMaker, Library, Recording
from fauxy.record import HeaderProcessor, Recorder, RecordingProxy
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route


async def _create_streaming_response(rec: Recording) -> Response:
    meta = json.loads(await (await rec.meta.open("r")).read())
    return StreamingResponse(
        await rec.response.open("rb"), meta["status"], meta["headers"]
    )


def create_proxy_route(handler: Callable[[Request], Awaitable[Response]]) -> Route:
    # Proxy all paths, ignoring the filled in path param
    # TODO let the path be specified to allow for different proxying behaviors for different paths
    # Not sure if we should mix multiple key behaviors in a single dir and how to handle the path
    # translation to the directory structure
    r = Route("/{_:path}", handler)

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
            return await _create_streaming_response(found)
        return Response("No replay found for ", status_code=424)

    return create_proxy_route(replay)


def proxy(
    base_url: str,
    library_dir: Path,
    key_maker: KeyMaker,
    header_processors: Optional[list[HeaderProcessor]] = None,
    response_processors: Optional[list[Callable[[Response], None]]] = None,
    disable_default_header_processors: Optional[bool] = False,
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
            return await _create_streaming_response(found)
        return await proxy.record(req)

    return create_proxy_route(proxy_once)


def app(routes: list[Route]) -> Starlette:
    return Starlette(debug=True, routes=routes)
