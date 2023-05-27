import json
import os
from typing import Optional
from anyio import Path
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from fauxy import KeyMaker
from fauxy.record import make_key_hash


class Library:
    def __init__(self, key_maker: KeyMaker, base_dir: Optional[Path] = None):
        self.key_maker = key_maker
        self.base_dir = base_dir

    async def find(self, req: Request):
        key = self.key_maker(req)
        _, hash = make_key_hash(key)
        if self.base_dir is None:
            self.base_dir = await Path.cwd()
        for dirpath, dirnames, filenames in os.walk(self.base_dir):
            if hash in dirnames:
                return Path(os.path.join(dirpath, hash))
        return None

    async def replay(self, req: Request):
        rec_dir = await self.find(req)
        if rec_dir is None:
            return Response(f"No recording for {req.url.path}", status_code=424)
        rec_meta = rec_dir / "meta.json"
        rec_content = rec_dir / "response.content"
        if not await rec_meta.exists():
            return Response(f"No meta.json in {rec_dir}", status_code=424)
        if not await rec_content.exists():
            return Response(f"No content in {rec_dir}", status_code=424)

        meta = json.loads(await (await rec_meta.open("r")).read())
        return StreamingResponse(
            await rec_content.open("rb"), meta["status"], meta["headers"]
        )
