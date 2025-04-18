from . import kv_pb2 as _kv_pb2
from . import auth_pb2 as _auth_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class AlarmType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    NONE: _ClassVar[AlarmType]
    NOSPACE: _ClassVar[AlarmType]
NONE: AlarmType
NOSPACE: AlarmType

class ResponseHeader(_message.Message):
    __slots__ = ("cluster_id", "member_id", "revision", "raft_term")
    CLUSTER_ID_FIELD_NUMBER: _ClassVar[int]
    MEMBER_ID_FIELD_NUMBER: _ClassVar[int]
    REVISION_FIELD_NUMBER: _ClassVar[int]
    RAFT_TERM_FIELD_NUMBER: _ClassVar[int]
    cluster_id: int
    member_id: int
    revision: int
    raft_term: int
    def __init__(self, cluster_id: _Optional[int] = ..., member_id: _Optional[int] = ..., revision: _Optional[int] = ..., raft_term: _Optional[int] = ...) -> None: ...

class RangeRequest(_message.Message):
    __slots__ = ("key", "range_end", "limit", "revision", "sort_order", "sort_target", "serializable", "keys_only", "count_only", "min_mod_revision", "max_mod_revision", "min_create_revision", "max_create_revision")
    class SortOrder(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        NONE: _ClassVar[RangeRequest.SortOrder]
        ASCEND: _ClassVar[RangeRequest.SortOrder]
        DESCEND: _ClassVar[RangeRequest.SortOrder]
    NONE: RangeRequest.SortOrder
    ASCEND: RangeRequest.SortOrder
    DESCEND: RangeRequest.SortOrder
    class SortTarget(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        KEY: _ClassVar[RangeRequest.SortTarget]
        VERSION: _ClassVar[RangeRequest.SortTarget]
        CREATE: _ClassVar[RangeRequest.SortTarget]
        MOD: _ClassVar[RangeRequest.SortTarget]
        VALUE: _ClassVar[RangeRequest.SortTarget]
    KEY: RangeRequest.SortTarget
    VERSION: RangeRequest.SortTarget
    CREATE: RangeRequest.SortTarget
    MOD: RangeRequest.SortTarget
    VALUE: RangeRequest.SortTarget
    KEY_FIELD_NUMBER: _ClassVar[int]
    RANGE_END_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    REVISION_FIELD_NUMBER: _ClassVar[int]
    SORT_ORDER_FIELD_NUMBER: _ClassVar[int]
    SORT_TARGET_FIELD_NUMBER: _ClassVar[int]
    SERIALIZABLE_FIELD_NUMBER: _ClassVar[int]
    KEYS_ONLY_FIELD_NUMBER: _ClassVar[int]
    COUNT_ONLY_FIELD_NUMBER: _ClassVar[int]
    MIN_MOD_REVISION_FIELD_NUMBER: _ClassVar[int]
    MAX_MOD_REVISION_FIELD_NUMBER: _ClassVar[int]
    MIN_CREATE_REVISION_FIELD_NUMBER: _ClassVar[int]
    MAX_CREATE_REVISION_FIELD_NUMBER: _ClassVar[int]
    key: bytes
    range_end: bytes
    limit: int
    revision: int
    sort_order: RangeRequest.SortOrder
    sort_target: RangeRequest.SortTarget
    serializable: bool
    keys_only: bool
    count_only: bool
    min_mod_revision: int
    max_mod_revision: int
    min_create_revision: int
    max_create_revision: int
    def __init__(self, key: _Optional[bytes] = ..., range_end: _Optional[bytes] = ..., limit: _Optional[int] = ..., revision: _Optional[int] = ..., sort_order: _Optional[_Union[RangeRequest.SortOrder, str]] = ..., sort_target: _Optional[_Union[RangeRequest.SortTarget, str]] = ..., serializable: bool = ..., keys_only: bool = ..., count_only: bool = ..., min_mod_revision: _Optional[int] = ..., max_mod_revision: _Optional[int] = ..., min_create_revision: _Optional[int] = ..., max_create_revision: _Optional[int] = ...) -> None: ...

class RangeResponse(_message.Message):
    __slots__ = ("header", "kvs", "more", "count")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    KVS_FIELD_NUMBER: _ClassVar[int]
    MORE_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    kvs: _containers.RepeatedCompositeFieldContainer[_kv_pb2.KeyValue]
    more: bool
    count: int
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., kvs: _Optional[_Iterable[_Union[_kv_pb2.KeyValue, _Mapping]]] = ..., more: bool = ..., count: _Optional[int] = ...) -> None: ...

class PutRequest(_message.Message):
    __slots__ = ("key", "value", "lease", "prev_kv", "ignore_value", "ignore_lease")
    KEY_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    LEASE_FIELD_NUMBER: _ClassVar[int]
    PREV_KV_FIELD_NUMBER: _ClassVar[int]
    IGNORE_VALUE_FIELD_NUMBER: _ClassVar[int]
    IGNORE_LEASE_FIELD_NUMBER: _ClassVar[int]
    key: bytes
    value: bytes
    lease: int
    prev_kv: bool
    ignore_value: bool
    ignore_lease: bool
    def __init__(self, key: _Optional[bytes] = ..., value: _Optional[bytes] = ..., lease: _Optional[int] = ..., prev_kv: bool = ..., ignore_value: bool = ..., ignore_lease: bool = ...) -> None: ...

class PutResponse(_message.Message):
    __slots__ = ("header", "prev_kv")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    PREV_KV_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    prev_kv: _kv_pb2.KeyValue
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., prev_kv: _Optional[_Union[_kv_pb2.KeyValue, _Mapping]] = ...) -> None: ...

class DeleteRangeRequest(_message.Message):
    __slots__ = ("key", "range_end", "prev_kv")
    KEY_FIELD_NUMBER: _ClassVar[int]
    RANGE_END_FIELD_NUMBER: _ClassVar[int]
    PREV_KV_FIELD_NUMBER: _ClassVar[int]
    key: bytes
    range_end: bytes
    prev_kv: bool
    def __init__(self, key: _Optional[bytes] = ..., range_end: _Optional[bytes] = ..., prev_kv: bool = ...) -> None: ...

class DeleteRangeResponse(_message.Message):
    __slots__ = ("header", "deleted", "prev_kvs")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    DELETED_FIELD_NUMBER: _ClassVar[int]
    PREV_KVS_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    deleted: int
    prev_kvs: _containers.RepeatedCompositeFieldContainer[_kv_pb2.KeyValue]
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., deleted: _Optional[int] = ..., prev_kvs: _Optional[_Iterable[_Union[_kv_pb2.KeyValue, _Mapping]]] = ...) -> None: ...

class RequestOp(_message.Message):
    __slots__ = ("request_range", "request_put", "request_delete_range", "request_txn")
    REQUEST_RANGE_FIELD_NUMBER: _ClassVar[int]
    REQUEST_PUT_FIELD_NUMBER: _ClassVar[int]
    REQUEST_DELETE_RANGE_FIELD_NUMBER: _ClassVar[int]
    REQUEST_TXN_FIELD_NUMBER: _ClassVar[int]
    request_range: RangeRequest
    request_put: PutRequest
    request_delete_range: DeleteRangeRequest
    request_txn: TxnRequest
    def __init__(self, request_range: _Optional[_Union[RangeRequest, _Mapping]] = ..., request_put: _Optional[_Union[PutRequest, _Mapping]] = ..., request_delete_range: _Optional[_Union[DeleteRangeRequest, _Mapping]] = ..., request_txn: _Optional[_Union[TxnRequest, _Mapping]] = ...) -> None: ...

class ResponseOp(_message.Message):
    __slots__ = ("response_range", "response_put", "response_delete_range", "response_txn")
    RESPONSE_RANGE_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_PUT_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_DELETE_RANGE_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_TXN_FIELD_NUMBER: _ClassVar[int]
    response_range: RangeResponse
    response_put: PutResponse
    response_delete_range: DeleteRangeResponse
    response_txn: TxnResponse
    def __init__(self, response_range: _Optional[_Union[RangeResponse, _Mapping]] = ..., response_put: _Optional[_Union[PutResponse, _Mapping]] = ..., response_delete_range: _Optional[_Union[DeleteRangeResponse, _Mapping]] = ..., response_txn: _Optional[_Union[TxnResponse, _Mapping]] = ...) -> None: ...

class Compare(_message.Message):
    __slots__ = ("result", "target", "key", "version", "create_revision", "mod_revision", "value", "range_end")
    class CompareResult(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        EQUAL: _ClassVar[Compare.CompareResult]
        GREATER: _ClassVar[Compare.CompareResult]
        LESS: _ClassVar[Compare.CompareResult]
        NOT_EQUAL: _ClassVar[Compare.CompareResult]
    EQUAL: Compare.CompareResult
    GREATER: Compare.CompareResult
    LESS: Compare.CompareResult
    NOT_EQUAL: Compare.CompareResult
    class CompareTarget(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        VERSION: _ClassVar[Compare.CompareTarget]
        CREATE: _ClassVar[Compare.CompareTarget]
        MOD: _ClassVar[Compare.CompareTarget]
        VALUE: _ClassVar[Compare.CompareTarget]
    VERSION: Compare.CompareTarget
    CREATE: Compare.CompareTarget
    MOD: Compare.CompareTarget
    VALUE: Compare.CompareTarget
    RESULT_FIELD_NUMBER: _ClassVar[int]
    TARGET_FIELD_NUMBER: _ClassVar[int]
    KEY_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    CREATE_REVISION_FIELD_NUMBER: _ClassVar[int]
    MOD_REVISION_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    RANGE_END_FIELD_NUMBER: _ClassVar[int]
    result: Compare.CompareResult
    target: Compare.CompareTarget
    key: bytes
    version: int
    create_revision: int
    mod_revision: int
    value: bytes
    range_end: bytes
    def __init__(self, result: _Optional[_Union[Compare.CompareResult, str]] = ..., target: _Optional[_Union[Compare.CompareTarget, str]] = ..., key: _Optional[bytes] = ..., version: _Optional[int] = ..., create_revision: _Optional[int] = ..., mod_revision: _Optional[int] = ..., value: _Optional[bytes] = ..., range_end: _Optional[bytes] = ...) -> None: ...

class TxnRequest(_message.Message):
    __slots__ = ("compare", "success", "failure")
    COMPARE_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    FAILURE_FIELD_NUMBER: _ClassVar[int]
    compare: _containers.RepeatedCompositeFieldContainer[Compare]
    success: _containers.RepeatedCompositeFieldContainer[RequestOp]
    failure: _containers.RepeatedCompositeFieldContainer[RequestOp]
    def __init__(self, compare: _Optional[_Iterable[_Union[Compare, _Mapping]]] = ..., success: _Optional[_Iterable[_Union[RequestOp, _Mapping]]] = ..., failure: _Optional[_Iterable[_Union[RequestOp, _Mapping]]] = ...) -> None: ...

class TxnResponse(_message.Message):
    __slots__ = ("header", "succeeded", "responses")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    SUCCEEDED_FIELD_NUMBER: _ClassVar[int]
    RESPONSES_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    succeeded: bool
    responses: _containers.RepeatedCompositeFieldContainer[ResponseOp]
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., succeeded: bool = ..., responses: _Optional[_Iterable[_Union[ResponseOp, _Mapping]]] = ...) -> None: ...

class CompactionRequest(_message.Message):
    __slots__ = ("revision", "physical")
    REVISION_FIELD_NUMBER: _ClassVar[int]
    PHYSICAL_FIELD_NUMBER: _ClassVar[int]
    revision: int
    physical: bool
    def __init__(self, revision: _Optional[int] = ..., physical: bool = ...) -> None: ...

class CompactionResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ...) -> None: ...

class HashRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class HashResponse(_message.Message):
    __slots__ = ("header", "hash")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    HASH_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    hash: int
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., hash: _Optional[int] = ...) -> None: ...

class HashKVRequest(_message.Message):
    __slots__ = ("revision",)
    REVISION_FIELD_NUMBER: _ClassVar[int]
    revision: int
    def __init__(self, revision: _Optional[int] = ...) -> None: ...

class HashKVResponse(_message.Message):
    __slots__ = ("header", "hash", "compact_revision")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    HASH_FIELD_NUMBER: _ClassVar[int]
    COMPACT_REVISION_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    hash: int
    compact_revision: int
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., hash: _Optional[int] = ..., compact_revision: _Optional[int] = ...) -> None: ...

class SnapshotRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class SnapshotResponse(_message.Message):
    __slots__ = ("header", "remaining_bytes", "blob")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    REMAINING_BYTES_FIELD_NUMBER: _ClassVar[int]
    BLOB_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    remaining_bytes: int
    blob: bytes
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., remaining_bytes: _Optional[int] = ..., blob: _Optional[bytes] = ...) -> None: ...

class WatchRequest(_message.Message):
    __slots__ = ("create_request", "cancel_request")
    CREATE_REQUEST_FIELD_NUMBER: _ClassVar[int]
    CANCEL_REQUEST_FIELD_NUMBER: _ClassVar[int]
    create_request: WatchCreateRequest
    cancel_request: WatchCancelRequest
    def __init__(self, create_request: _Optional[_Union[WatchCreateRequest, _Mapping]] = ..., cancel_request: _Optional[_Union[WatchCancelRequest, _Mapping]] = ...) -> None: ...

class WatchCreateRequest(_message.Message):
    __slots__ = ("key", "range_end", "start_revision", "progress_notify", "filters", "prev_kv")
    class FilterType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        NOPUT: _ClassVar[WatchCreateRequest.FilterType]
        NODELETE: _ClassVar[WatchCreateRequest.FilterType]
    NOPUT: WatchCreateRequest.FilterType
    NODELETE: WatchCreateRequest.FilterType
    KEY_FIELD_NUMBER: _ClassVar[int]
    RANGE_END_FIELD_NUMBER: _ClassVar[int]
    START_REVISION_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_NOTIFY_FIELD_NUMBER: _ClassVar[int]
    FILTERS_FIELD_NUMBER: _ClassVar[int]
    PREV_KV_FIELD_NUMBER: _ClassVar[int]
    key: bytes
    range_end: bytes
    start_revision: int
    progress_notify: bool
    filters: _containers.RepeatedScalarFieldContainer[WatchCreateRequest.FilterType]
    prev_kv: bool
    def __init__(self, key: _Optional[bytes] = ..., range_end: _Optional[bytes] = ..., start_revision: _Optional[int] = ..., progress_notify: bool = ..., filters: _Optional[_Iterable[_Union[WatchCreateRequest.FilterType, str]]] = ..., prev_kv: bool = ...) -> None: ...

class WatchCancelRequest(_message.Message):
    __slots__ = ("watch_id",)
    WATCH_ID_FIELD_NUMBER: _ClassVar[int]
    watch_id: int
    def __init__(self, watch_id: _Optional[int] = ...) -> None: ...

class WatchResponse(_message.Message):
    __slots__ = ("header", "watch_id", "created", "canceled", "compact_revision", "cancel_reason", "events")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    WATCH_ID_FIELD_NUMBER: _ClassVar[int]
    CREATED_FIELD_NUMBER: _ClassVar[int]
    CANCELED_FIELD_NUMBER: _ClassVar[int]
    COMPACT_REVISION_FIELD_NUMBER: _ClassVar[int]
    CANCEL_REASON_FIELD_NUMBER: _ClassVar[int]
    EVENTS_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    watch_id: int
    created: bool
    canceled: bool
    compact_revision: int
    cancel_reason: str
    events: _containers.RepeatedCompositeFieldContainer[_kv_pb2.Event]
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., watch_id: _Optional[int] = ..., created: bool = ..., canceled: bool = ..., compact_revision: _Optional[int] = ..., cancel_reason: _Optional[str] = ..., events: _Optional[_Iterable[_Union[_kv_pb2.Event, _Mapping]]] = ...) -> None: ...

class LeaseGrantRequest(_message.Message):
    __slots__ = ("TTL", "ID")
    TTL_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    TTL: int
    ID: int
    def __init__(self, TTL: _Optional[int] = ..., ID: _Optional[int] = ...) -> None: ...

class LeaseGrantResponse(_message.Message):
    __slots__ = ("header", "ID", "TTL", "error")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    TTL_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    ID: int
    TTL: int
    error: str
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., ID: _Optional[int] = ..., TTL: _Optional[int] = ..., error: _Optional[str] = ...) -> None: ...

class LeaseRevokeRequest(_message.Message):
    __slots__ = ("ID",)
    ID_FIELD_NUMBER: _ClassVar[int]
    ID: int
    def __init__(self, ID: _Optional[int] = ...) -> None: ...

class LeaseRevokeResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ...) -> None: ...

class LeaseKeepAliveRequest(_message.Message):
    __slots__ = ("ID",)
    ID_FIELD_NUMBER: _ClassVar[int]
    ID: int
    def __init__(self, ID: _Optional[int] = ...) -> None: ...

class LeaseKeepAliveResponse(_message.Message):
    __slots__ = ("header", "ID", "TTL")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    TTL_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    ID: int
    TTL: int
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., ID: _Optional[int] = ..., TTL: _Optional[int] = ...) -> None: ...

class LeaseTimeToLiveRequest(_message.Message):
    __slots__ = ("ID", "keys")
    ID_FIELD_NUMBER: _ClassVar[int]
    KEYS_FIELD_NUMBER: _ClassVar[int]
    ID: int
    keys: bool
    def __init__(self, ID: _Optional[int] = ..., keys: bool = ...) -> None: ...

class LeaseTimeToLiveResponse(_message.Message):
    __slots__ = ("header", "ID", "TTL", "grantedTTL", "keys")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    TTL_FIELD_NUMBER: _ClassVar[int]
    GRANTEDTTL_FIELD_NUMBER: _ClassVar[int]
    KEYS_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    ID: int
    TTL: int
    grantedTTL: int
    keys: _containers.RepeatedScalarFieldContainer[bytes]
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., ID: _Optional[int] = ..., TTL: _Optional[int] = ..., grantedTTL: _Optional[int] = ..., keys: _Optional[_Iterable[bytes]] = ...) -> None: ...

class Member(_message.Message):
    __slots__ = ("ID", "name", "peerURLs", "clientURLs")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    PEERURLS_FIELD_NUMBER: _ClassVar[int]
    CLIENTURLS_FIELD_NUMBER: _ClassVar[int]
    ID: int
    name: str
    peerURLs: _containers.RepeatedScalarFieldContainer[str]
    clientURLs: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, ID: _Optional[int] = ..., name: _Optional[str] = ..., peerURLs: _Optional[_Iterable[str]] = ..., clientURLs: _Optional[_Iterable[str]] = ...) -> None: ...

class MemberAddRequest(_message.Message):
    __slots__ = ("peerURLs",)
    PEERURLS_FIELD_NUMBER: _ClassVar[int]
    peerURLs: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, peerURLs: _Optional[_Iterable[str]] = ...) -> None: ...

class MemberAddResponse(_message.Message):
    __slots__ = ("header", "member", "members")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    MEMBER_FIELD_NUMBER: _ClassVar[int]
    MEMBERS_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    member: Member
    members: _containers.RepeatedCompositeFieldContainer[Member]
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., member: _Optional[_Union[Member, _Mapping]] = ..., members: _Optional[_Iterable[_Union[Member, _Mapping]]] = ...) -> None: ...

class MemberRemoveRequest(_message.Message):
    __slots__ = ("ID",)
    ID_FIELD_NUMBER: _ClassVar[int]
    ID: int
    def __init__(self, ID: _Optional[int] = ...) -> None: ...

class MemberRemoveResponse(_message.Message):
    __slots__ = ("header", "members")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    MEMBERS_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    members: _containers.RepeatedCompositeFieldContainer[Member]
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., members: _Optional[_Iterable[_Union[Member, _Mapping]]] = ...) -> None: ...

class MemberUpdateRequest(_message.Message):
    __slots__ = ("ID", "peerURLs")
    ID_FIELD_NUMBER: _ClassVar[int]
    PEERURLS_FIELD_NUMBER: _ClassVar[int]
    ID: int
    peerURLs: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, ID: _Optional[int] = ..., peerURLs: _Optional[_Iterable[str]] = ...) -> None: ...

class MemberUpdateResponse(_message.Message):
    __slots__ = ("header", "members")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    MEMBERS_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    members: _containers.RepeatedCompositeFieldContainer[Member]
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., members: _Optional[_Iterable[_Union[Member, _Mapping]]] = ...) -> None: ...

class MemberListRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class MemberListResponse(_message.Message):
    __slots__ = ("header", "members")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    MEMBERS_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    members: _containers.RepeatedCompositeFieldContainer[Member]
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., members: _Optional[_Iterable[_Union[Member, _Mapping]]] = ...) -> None: ...

class DefragmentRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class DefragmentResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ...) -> None: ...

class MoveLeaderRequest(_message.Message):
    __slots__ = ("targetID",)
    TARGETID_FIELD_NUMBER: _ClassVar[int]
    targetID: int
    def __init__(self, targetID: _Optional[int] = ...) -> None: ...

class MoveLeaderResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ...) -> None: ...

class AlarmRequest(_message.Message):
    __slots__ = ("action", "memberID", "alarm")
    class AlarmAction(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        GET: _ClassVar[AlarmRequest.AlarmAction]
        ACTIVATE: _ClassVar[AlarmRequest.AlarmAction]
        DEACTIVATE: _ClassVar[AlarmRequest.AlarmAction]
    GET: AlarmRequest.AlarmAction
    ACTIVATE: AlarmRequest.AlarmAction
    DEACTIVATE: AlarmRequest.AlarmAction
    ACTION_FIELD_NUMBER: _ClassVar[int]
    MEMBERID_FIELD_NUMBER: _ClassVar[int]
    ALARM_FIELD_NUMBER: _ClassVar[int]
    action: AlarmRequest.AlarmAction
    memberID: int
    alarm: AlarmType
    def __init__(self, action: _Optional[_Union[AlarmRequest.AlarmAction, str]] = ..., memberID: _Optional[int] = ..., alarm: _Optional[_Union[AlarmType, str]] = ...) -> None: ...

class AlarmMember(_message.Message):
    __slots__ = ("memberID", "alarm")
    MEMBERID_FIELD_NUMBER: _ClassVar[int]
    ALARM_FIELD_NUMBER: _ClassVar[int]
    memberID: int
    alarm: AlarmType
    def __init__(self, memberID: _Optional[int] = ..., alarm: _Optional[_Union[AlarmType, str]] = ...) -> None: ...

class AlarmResponse(_message.Message):
    __slots__ = ("header", "alarms")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    ALARMS_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    alarms: _containers.RepeatedCompositeFieldContainer[AlarmMember]
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., alarms: _Optional[_Iterable[_Union[AlarmMember, _Mapping]]] = ...) -> None: ...

class StatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class StatusResponse(_message.Message):
    __slots__ = ("header", "version", "dbSize", "leader", "raftIndex", "raftTerm")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    DBSIZE_FIELD_NUMBER: _ClassVar[int]
    LEADER_FIELD_NUMBER: _ClassVar[int]
    RAFTINDEX_FIELD_NUMBER: _ClassVar[int]
    RAFTTERM_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    version: str
    dbSize: int
    leader: int
    raftIndex: int
    raftTerm: int
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., version: _Optional[str] = ..., dbSize: _Optional[int] = ..., leader: _Optional[int] = ..., raftIndex: _Optional[int] = ..., raftTerm: _Optional[int] = ...) -> None: ...

class AuthEnableRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class AuthDisableRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class AuthenticateRequest(_message.Message):
    __slots__ = ("name", "password")
    NAME_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    name: str
    password: str
    def __init__(self, name: _Optional[str] = ..., password: _Optional[str] = ...) -> None: ...

class AuthUserAddRequest(_message.Message):
    __slots__ = ("name", "password")
    NAME_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    name: str
    password: str
    def __init__(self, name: _Optional[str] = ..., password: _Optional[str] = ...) -> None: ...

class AuthUserGetRequest(_message.Message):
    __slots__ = ("name",)
    NAME_FIELD_NUMBER: _ClassVar[int]
    name: str
    def __init__(self, name: _Optional[str] = ...) -> None: ...

class AuthUserDeleteRequest(_message.Message):
    __slots__ = ("name",)
    NAME_FIELD_NUMBER: _ClassVar[int]
    name: str
    def __init__(self, name: _Optional[str] = ...) -> None: ...

class AuthUserChangePasswordRequest(_message.Message):
    __slots__ = ("name", "password")
    NAME_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    name: str
    password: str
    def __init__(self, name: _Optional[str] = ..., password: _Optional[str] = ...) -> None: ...

class AuthUserGrantRoleRequest(_message.Message):
    __slots__ = ("user", "role")
    USER_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    user: str
    role: str
    def __init__(self, user: _Optional[str] = ..., role: _Optional[str] = ...) -> None: ...

class AuthUserRevokeRoleRequest(_message.Message):
    __slots__ = ("name", "role")
    NAME_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    name: str
    role: str
    def __init__(self, name: _Optional[str] = ..., role: _Optional[str] = ...) -> None: ...

class AuthRoleAddRequest(_message.Message):
    __slots__ = ("name",)
    NAME_FIELD_NUMBER: _ClassVar[int]
    name: str
    def __init__(self, name: _Optional[str] = ...) -> None: ...

class AuthRoleGetRequest(_message.Message):
    __slots__ = ("role",)
    ROLE_FIELD_NUMBER: _ClassVar[int]
    role: str
    def __init__(self, role: _Optional[str] = ...) -> None: ...

class AuthUserListRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class AuthRoleListRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class AuthRoleDeleteRequest(_message.Message):
    __slots__ = ("role",)
    ROLE_FIELD_NUMBER: _ClassVar[int]
    role: str
    def __init__(self, role: _Optional[str] = ...) -> None: ...

class AuthRoleGrantPermissionRequest(_message.Message):
    __slots__ = ("name", "perm")
    NAME_FIELD_NUMBER: _ClassVar[int]
    PERM_FIELD_NUMBER: _ClassVar[int]
    name: str
    perm: _auth_pb2.Permission
    def __init__(self, name: _Optional[str] = ..., perm: _Optional[_Union[_auth_pb2.Permission, _Mapping]] = ...) -> None: ...

class AuthRoleRevokePermissionRequest(_message.Message):
    __slots__ = ("role", "key", "range_end")
    ROLE_FIELD_NUMBER: _ClassVar[int]
    KEY_FIELD_NUMBER: _ClassVar[int]
    RANGE_END_FIELD_NUMBER: _ClassVar[int]
    role: str
    key: str
    range_end: str
    def __init__(self, role: _Optional[str] = ..., key: _Optional[str] = ..., range_end: _Optional[str] = ...) -> None: ...

class AuthEnableResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ...) -> None: ...

class AuthDisableResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ...) -> None: ...

class AuthenticateResponse(_message.Message):
    __slots__ = ("header", "token")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    token: str
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., token: _Optional[str] = ...) -> None: ...

class AuthUserAddResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ...) -> None: ...

class AuthUserGetResponse(_message.Message):
    __slots__ = ("header", "roles")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    ROLES_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    roles: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., roles: _Optional[_Iterable[str]] = ...) -> None: ...

class AuthUserDeleteResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ...) -> None: ...

class AuthUserChangePasswordResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ...) -> None: ...

class AuthUserGrantRoleResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ...) -> None: ...

class AuthUserRevokeRoleResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ...) -> None: ...

class AuthRoleAddResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ...) -> None: ...

class AuthRoleGetResponse(_message.Message):
    __slots__ = ("header", "perm")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    PERM_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    perm: _containers.RepeatedCompositeFieldContainer[_auth_pb2.Permission]
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., perm: _Optional[_Iterable[_Union[_auth_pb2.Permission, _Mapping]]] = ...) -> None: ...

class AuthRoleListResponse(_message.Message):
    __slots__ = ("header", "roles")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    ROLES_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    roles: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., roles: _Optional[_Iterable[str]] = ...) -> None: ...

class AuthUserListResponse(_message.Message):
    __slots__ = ("header", "users")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    USERS_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    users: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ..., users: _Optional[_Iterable[str]] = ...) -> None: ...

class AuthRoleDeleteResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ...) -> None: ...

class AuthRoleGrantPermissionResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ...) -> None: ...

class AuthRoleRevokePermissionResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: _Optional[_Union[ResponseHeader, _Mapping]] = ...) -> None: ...
