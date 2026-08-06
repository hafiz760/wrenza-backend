from typing import Annotated

# pyrefly: ignore [missing-import]
from pydantic import Field

from app.schemas.common import CamelModel


class ProductImageOut(CamelModel):
    id: str
    url: Annotated[str, Field(min_length=1, max_length=500)]
    alt: Annotated[str, Field(max_length=255)]
    width: Annotated[int, Field(ge=0)]
    height: Annotated[int, Field(ge=0)]


class ProductImageCreate(CamelModel):
    url: Annotated[str, Field(min_length=1, max_length=500)]
    alt: Annotated[str, Field(max_length=255)] = ""
    width: Annotated[int, Field(ge=0)] = 0
    height: Annotated[int, Field(ge=0)] = 0
    position: Annotated[int, Field(ge=0)] = 0
