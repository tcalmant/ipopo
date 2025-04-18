from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class KeyValue(_message.Message):
    __slots__ = ("key", "create_revision", "mod_revision", "version", "value", "lease")
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
    def __init__(self, key: _Optional[bytes] = ..., create_revision: _Optional[int] = ..., mod_revision: _Optional[int] = ..., version: _Optional[int] = ..., value: _Optional[bytes] = ..., lease: _Optional[int] = ...) -> None: ...

class Event(_message.Message):
    __slots__ = ("type", "kv", "prev_kv")
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
    def __init__(self, type: _Optional[_Union[Event.EventType, str]] = ..., kv: _Optional[_Union[KeyValue, _Mapping]] = ..., prev_kv: _Optional[_Union[KeyValue, _Mapping]] = ...) -> None: ...
