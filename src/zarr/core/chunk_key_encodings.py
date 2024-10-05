from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypedDict, cast

from zarr.abc.metadata import Metadata
from zarr.core.common import (
    JSON,
    ChunkCoords,
    parse_named_configuration,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

SeparatorLiteral = Literal[".", "/"]


def parse_separator(data: JSON) -> SeparatorLiteral:
    if data not in (".", "/"):
        raise ValueError(f"Expected an '.' or '/' separator. Got {data} instead.")
    return cast(SeparatorLiteral, data)


class ChunkKeyEncodingDict(TypedDict):
    """A dictionary representing a chunk key encoding configuration."""

    name: str
    configuration: Mapping[Literal["separator"], SeparatorLiteral]


@dataclass(frozen=True)
class ChunkKeyEncoding(Metadata[ChunkKeyEncodingDict]):
    name: str
    separator: SeparatorLiteral = "."

    def __init__(self, *, separator: SeparatorLiteral) -> None:
        separator_parsed = parse_separator(separator)

        object.__setattr__(self, "separator", separator_parsed)

    @classmethod
    def from_dict(cls, data: ChunkKeyEncodingDict | ChunkKeyEncoding) -> ChunkKeyEncoding:
        if isinstance(data, ChunkKeyEncoding):
            return data

        _data = dict(data)

        # configuration is optional for chunk key encodings
        name_parsed, config_parsed = parse_named_configuration(_data, require_configuration=False)  # type: ignore[arg-type]
        if name_parsed == "default":
            if config_parsed is None:
                # for default, normalize missing configuration to use the "/" separator.
                config_parsed = {"separator": "/"}
            return DefaultChunkKeyEncoding(**config_parsed)  # type: ignore[arg-type]
        if name_parsed == "v2":
            if config_parsed is None:
                # for v2, normalize missing configuration to use the "." separator.
                config_parsed = {"separator": "."}
            return V2ChunkKeyEncoding(**config_parsed)  # type: ignore[arg-type]
        msg = f"Unknown chunk key encoding. Got {name_parsed}, expected one of ('v2', 'default')."
        raise ValueError(msg)

    def to_dict(self) -> ChunkKeyEncodingDict:
        out_dict = {"name": self.name, "configuration": {"separator": self.separator}}
        return cast(ChunkKeyEncodingDict, out_dict)

    @abstractmethod
    def decode_chunk_key(self, chunk_key: str) -> ChunkCoords:
        pass

    @abstractmethod
    def encode_chunk_key(self, chunk_coords: ChunkCoords) -> str:
        pass


@dataclass(frozen=True)
class DefaultChunkKeyEncoding(ChunkKeyEncoding):
    name: Literal["default"] = "default"

    def decode_chunk_key(self, chunk_key: str) -> ChunkCoords:
        if chunk_key == "c":
            return ()
        return tuple(map(int, chunk_key[1:].split(self.separator)))

    def encode_chunk_key(self, chunk_coords: ChunkCoords) -> str:
        return self.separator.join(map(str, ("c",) + chunk_coords))


@dataclass(frozen=True)
class V2ChunkKeyEncoding(ChunkKeyEncoding):
    name: Literal["v2"] = "v2"

    def decode_chunk_key(self, chunk_key: str) -> ChunkCoords:
        return tuple(map(int, chunk_key.split(self.separator)))

    def encode_chunk_key(self, chunk_coords: ChunkCoords) -> str:
        chunk_identifier = self.separator.join(map(str, chunk_coords))
        return "0" if chunk_identifier == "" else chunk_identifier
