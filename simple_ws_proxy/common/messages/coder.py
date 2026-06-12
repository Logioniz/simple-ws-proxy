"""Generic JSON encoder/decoder helpers for msgspec.Struct messages."""

from typing import Type, TypeVar

import msgspec
import msgspec.json

T = TypeVar('T', bound=msgspec.Struct)


def encode(msg: msgspec.Struct) -> bytes:
    """Serialize any :class:`msgspec.Struct` instance to JSON bytes.

    Args:
        msg: The struct instance to encode.

    Returns:
        JSON-encoded bytes.
    """
    return msgspec.json.encode(msg)


def decode(data: bytes, typ: Type[T]) -> T:
    """Deserialize JSON bytes into a :class:`msgspec.Struct` instance.

    Args:
        data: Raw JSON bytes.
        typ:  Target :class:`msgspec.Struct` subclass.

    Returns:
        Decoded instance of *typ*.

    Raises:
        msgspec.ValidationError: If *data* does not match the schema of *typ*.
    """
    return msgspec.json.decode(data, type=typ)
