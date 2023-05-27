from typing import (
    Any,
    AsyncIterator,
    Callable,
    Optional,
    Tuple,
    TypeAlias,
)

from starlette.requests import Request

JSON: TypeAlias = dict[str, "JSON"] | list["JSON"] | str | int | float | bool | None
KeyMaker: TypeAlias = Callable[[Request], JSON]
