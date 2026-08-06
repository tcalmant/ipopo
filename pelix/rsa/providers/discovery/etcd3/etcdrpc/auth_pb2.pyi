from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper

DESCRIPTOR: _descriptor.FileDescriptor

class User(_message.Message):
    __slots__ = ("name", "password", "roles")
    NAME_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    ROLES_FIELD_NUMBER: _ClassVar[int]
    name: bytes
    password: bytes
    roles: _containers.RepeatedScalarFieldContainer[str]
    def __init__(
        self,
        name: bytes | None = ...,
        password: bytes | None = ...,
        roles: _Iterable[str] | None = ...,
    ) -> None: ...

class Permission(_message.Message):
    __slots__ = ("key", "permType", "range_end")
    class Type(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        READ: _ClassVar[Permission.Type]
        WRITE: _ClassVar[Permission.Type]
        READWRITE: _ClassVar[Permission.Type]

    READ: Permission.Type
    WRITE: Permission.Type
    READWRITE: Permission.Type
    PERMTYPE_FIELD_NUMBER: _ClassVar[int]
    KEY_FIELD_NUMBER: _ClassVar[int]
    RANGE_END_FIELD_NUMBER: _ClassVar[int]
    permType: Permission.Type
    key: bytes
    range_end: bytes
    def __init__(
        self,
        permType: Permission.Type | str | None = ...,
        key: bytes | None = ...,
        range_end: bytes | None = ...,
    ) -> None: ...

class Role(_message.Message):
    __slots__ = ("keyPermission", "name")
    NAME_FIELD_NUMBER: _ClassVar[int]
    KEYPERMISSION_FIELD_NUMBER: _ClassVar[int]
    name: bytes
    keyPermission: _containers.RepeatedCompositeFieldContainer[Permission]
    def __init__(
        self,
        name: bytes | None = ...,
        keyPermission: _Iterable[Permission | _Mapping] | None = ...,
    ) -> None: ...
