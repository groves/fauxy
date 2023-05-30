import uvicorn
from starlette.requests import Request
from fauxy.app import app, proxy
from fauxy.library import JSON
from fauxy.record import strip_headers


def path_and_query_key(req: Request) -> JSON:
    return {"path": req.url.path, "safe": "safe-mode" in req.query_params}


fauxy = app(
    routes=[
        proxy(
            base_url="https://v2.jokeapi.dev",
            library_dir="recordings",
            key_maker=path_and_query_key,
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
    ]
)

if __name__ == "__main__":
    uvicorn.run("example:fauxy", port=47624, reload=True)
