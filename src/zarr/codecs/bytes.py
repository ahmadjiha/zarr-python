from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING

import numpy as np

from zarr.abc.codec import ArrayBytesCodec, CodecConfigDict, CodecDict
from zarr.core.buffer import Buffer, NDArrayLike, NDBuffer
from zarr.core.common import parse_enum, parse_named_configuration
from zarr.registry import register_codec

if TYPE_CHECKING:
    from typing import Literal, Self

    from zarr.core.array_spec import ArraySpec


class Endian(Enum):
    """
    Enum for endian type used by bytes codec.
    """

    big = "big"
    little = "little"


default_system_endian = Endian(sys.byteorder)


class BytesCodecConfigDict(CodecConfigDict):
    """A dictionary representing a bytes codec configuration."""

    # TODO: Why not type this w/ the Endian Enum
    endian: Literal["big", "little"]


class BytesCodecDict(CodecDict[BytesCodecConfigDict]):
    """A dictionary representing a bytes codec."""

    ...


@dataclass(frozen=True)
class BytesCodec(ArrayBytesCodec[BytesCodecDict]):
    is_fixed_size = True

    endian: Endian | None

    def __init__(self, *, endian: Endian | str | None = default_system_endian) -> None:
        endian_parsed = None if endian is None else parse_enum(endian, Endian)

        object.__setattr__(self, "endian", endian_parsed)

    @classmethod
    def from_dict(cls, data: BytesCodecDict) -> Self:
        _, configuration_parsed = parse_named_configuration(
            data, "bytes", require_configuration=False
        )

        configuration_parsed = configuration_parsed or {}
        return cls(**configuration_parsed)  # type: ignore[arg-type]

    def to_dict(self) -> BytesCodecDict:
        out_dict: BytesCodecDict = {"name": "bytes"}
        if self.endian is not None:
            out_dict["configuration"] = {"endian": self.endian.value}

        return out_dict

    def evolve_from_array_spec(self, array_spec: ArraySpec) -> Self:
        if array_spec.dtype.itemsize == 0:
            if self.endian is not None:
                return replace(self, endian=None)
        elif self.endian is None:
            raise ValueError(
                "The `endian` configuration needs to be specified for multi-byte data types."
            )
        return self

    async def _decode_single(
        self,
        chunk_bytes: Buffer,
        chunk_spec: ArraySpec,
    ) -> NDBuffer:
        assert isinstance(chunk_bytes, Buffer)
        if chunk_spec.dtype.itemsize > 0:
            if self.endian == Endian.little:
                prefix = "<"
            else:
                prefix = ">"
            dtype = np.dtype(f"{prefix}{chunk_spec.dtype.str[1:]}")
        else:
            dtype = np.dtype(f"|{chunk_spec.dtype.str[1:]}")

        as_array_like = chunk_bytes.as_array_like()
        if isinstance(as_array_like, NDArrayLike):
            as_nd_array_like = as_array_like
        else:
            as_nd_array_like = np.asanyarray(as_array_like)
        chunk_array = chunk_spec.prototype.nd_buffer.from_ndarray_like(
            as_nd_array_like.view(dtype=dtype)
        )

        # ensure correct chunk shape
        if chunk_array.shape != chunk_spec.shape:
            chunk_array = chunk_array.reshape(
                chunk_spec.shape,
            )
        return chunk_array

    async def _encode_single(
        self,
        chunk_array: NDBuffer,
        chunk_spec: ArraySpec,
    ) -> Buffer | None:
        assert isinstance(chunk_array, NDBuffer)
        if (
            chunk_array.dtype.itemsize > 1
            and self.endian is not None
            and self.endian != chunk_array.byteorder
        ):
            # type-ignore is a numpy bug
            # see https://github.com/numpy/numpy/issues/26473
            new_dtype = chunk_array.dtype.newbyteorder(self.endian.name)  # type: ignore[arg-type]
            chunk_array = chunk_array.astype(new_dtype)

        nd_array = chunk_array.as_ndarray_like()
        # Flatten the nd-array (only copy if needed) and reinterpret as bytes
        nd_array = nd_array.ravel().view(dtype="b")
        return chunk_spec.prototype.buffer.from_array_like(nd_array)

    def compute_encoded_size(self, input_byte_length: int, _chunk_spec: ArraySpec) -> int:
        return input_byte_length


register_codec("bytes", BytesCodec)

# compatibility with earlier versions of ZEP1
register_codec("endian", BytesCodec)
