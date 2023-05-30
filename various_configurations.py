from anyio import Path
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Route
from fauxy.app import app, create_proxy_route, proxy, replay
from fauxy.library import JSON, Library

from fauxy.record import Recorder, RecordingProxy, strip_headers


def path_and_query_key(req: Request) -> JSON:
    return {"path": req.url.path, "safe": "safe-mode" in req.query_params}


library_dir = Path(".")
library = Library(library_dir, path_and_query_key)
base_url = "https://v2.jokeapi.dev"
hp = [
    strip_headers(
        "content-length",
        "cf-ray",
        "retry-after",
        "ratelimit-remaining",
        "ratelimit-reset",
        "report-to",
    )
]
rp = RecordingProxy(
    base_url=base_url,
    library=library,
    header_processors=hp,
)

record_only = app(routes=[create_proxy_route(rp.record)])
replay_only = app(routes=[replay(library_dir, path_and_query_key)])
replay_or_record = app(
    routes=[proxy(base_url, library_dir, path_and_query_key, header_processors=hp)]
)
