from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper

DESCRIPTOR: _descriptor.FileDescriptor

class KeyValue(_message.Message):
    __slots__ = ("create_revision", "key", "lease", "mod_revision", "value", "version")
    KEY_FIELD_NUMBER: _ClassVar[int]
    CREATE_REVISION_FIELD_NUMBER: _ClassVar[int]
    MOD_REVISION_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    LEASE_FIELD_NUMBER: _ClassVar[int]
    key: bytes
    create_revision: int
    mod_revision: int
    version: int
    value: bytes
    lease: int
    def __init__(
        self,
        key: bytes | None = ...,
        create_revision: int | None = ...,
        mod_revision: int | None = ...,
        version: int | None = ...,
        value: bytes | None = ...,
        lease: int | None = ...,
    ) -> None: ...

class Event(_message.Message):
    __slots__ = ("kv", "prev_kv", "type")
    class EventType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        PUT: _ClassVar[Event.EventType]
        DELETE: _ClassVar[Event.EventType]

    PUT: Event.EventType
    DELETE: Event.EventType
    TYPE_FIELD_NUMBER: _ClassVar[int]
    KV_FIELD_NUMBER: _ClassVar[int]
    PREV_KV_FIELD_NUMBER: _ClassVar[int]
    type: Event.EventType
    kv: KeyValue
    prev_kv: KeyValue
    def __init__(
        self,
        type: Event.EventType | str | None = ...,
        kv: KeyValue | _Mapping | None = ...,
        prev_kv: KeyValue | _Mapping | None = ...,
    ) -> None: ...
