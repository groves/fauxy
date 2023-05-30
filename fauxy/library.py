from asyncio import iscoroutine
from hashlib import blake2b
import json
import os
from typing import Awaitable, Callable, Coroutine, TypeAlias, Optional, Tuple
from anyio import Path
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

JSON: TypeAlias = dict[str, "JSON"] | list["JSON"] | str | int | float | bool | None
KeyMaker: TypeAlias = (
    Callable[[Request], JSON]
    | Callable[
        [Request],
        Awaitable[JSON],
    ]
)


class Recording:
    def __init__(self, rec_dir: Path):
        self.rec_dir = rec_dir

    @property
    def meta(self) -> Path:
        return self.rec_dir / "meta.json"

    @property
    def response(self) -> Path:
        return self.rec_dir / "response.content"

    @property
    def key(self) -> Path:
        return self.rec_dir / "key.json"

    async def exists(self) -> bool:
        return await self.meta.exists() and await self.response.exists()


class Library:
    def __init__(self, base_dir: Path | str, key_maker: KeyMaker):
        self.key_maker = key_maker
        self.base_dir = base_dir if isinstance(base_dir, Path) else Path(base_dir)

    async def _make_key_hash(self, req: Request):
        key = self.key_maker(req)
        if iscoroutine(key):
            key = await key
        key_bytes = json.dumps(key, indent=2).encode()

        hash = blake2b(digest_size=4)
        hash.update(key_bytes)
        return key_bytes, hash.hexdigest()

    async def create(self, req: Request) -> Tuple[Recording, bytes]:
        key_bytes, hash = await self._make_key_hash(req)
        rec_dir = self.base_dir / req.url.path[1:] / hash
        await rec_dir.mkdir(parents=True, exist_ok=True)
        return Recording(rec_dir), key_bytes

    async def find(self, req: Request) -> Optional[Recording]:
        _, hash = await self._make_key_hash(req)
        for dirpath, dirnames, filenames in os.walk(self.base_dir):
            if hash in dirnames:
                rec = Recording(Path(os.path.join(dirpath, hash)))
                if await rec.exists():
                    return rec
        return None
