from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Route
from fauxy import ProxyOnce

from fauxy.record import JSON, Recorder, strip_headers
from fauxy.replay import Library


def path_and_query_key(req: Request) -> JSON:
    return {"path": req.url.path, "safe": "safe-mode" in req.query_params}


recorder = Recorder(
    "https://v2.jokeapi.dev",
    path_and_query_key,
    header_processors=[
        strip_headers(
            "content-length",
            "cf-ray",
            "retry-after",
            "ratelimit-remaining",
            "ratelimit-reset",
            "report-to",
        )
    ],
)
record = Starlette(
    debug=True,
    routes=[
        Route("/{path:path}", recorder.record),
    ],
)
library = Library(path_and_query_key)
replay = Starlette(
    debug=True,
    routes=[
        Route("/{path:path}", library.replay),
    ],
)
proxy = ProxyOnce(recorder, library)
proxy_once = Starlette(debug=True, routes=[Route("/{path:path}", proxy.serve)])
