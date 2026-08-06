from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper

from . import auth_pb2 as _auth_pb2
from . import kv_pb2 as _kv_pb2

DESCRIPTOR: _descriptor.FileDescriptor

class AlarmType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    NONE: _ClassVar[AlarmType]
    NOSPACE: _ClassVar[AlarmType]

NONE: AlarmType
NOSPACE: AlarmType

class ResponseHeader(_message.Message):
    __slots__ = ("cluster_id", "member_id", "raft_term", "revision")
    CLUSTER_ID_FIELD_NUMBER: _ClassVar[int]
    MEMBER_ID_FIELD_NUMBER: _ClassVar[int]
    REVISION_FIELD_NUMBER: _ClassVar[int]
    RAFT_TERM_FIELD_NUMBER: _ClassVar[int]
    cluster_id: int
    member_id: int
    revision: int
    raft_term: int
    def __init__(
        self,
        cluster_id: int | None = ...,
        member_id: int | None = ...,
        revision: int | None = ...,
        raft_term: int | None = ...,
    ) -> None: ...

class RangeRequest(_message.Message):
    __slots__ = (
        "count_only",
        "key",
        "keys_only",
        "limit",
        "max_create_revision",
        "max_mod_revision",
        "min_create_revision",
        "min_mod_revision",
        "range_end",
        "revision",
        "serializable",
        "sort_order",
        "sort_target",
    )
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
    def __init__(
        self,
        key: bytes | None = ...,
        range_end: bytes | None = ...,
        limit: int | None = ...,
        revision: int | None = ...,
        sort_order: RangeRequest.SortOrder | str | None = ...,
        sort_target: RangeRequest.SortTarget | str | None = ...,
        serializable: bool = ...,
        keys_only: bool = ...,
        count_only: bool = ...,
        min_mod_revision: int | None = ...,
        max_mod_revision: int | None = ...,
        min_create_revision: int | None = ...,
        max_create_revision: int | None = ...,
    ) -> None: ...

class RangeResponse(_message.Message):
    __slots__ = ("count", "header", "kvs", "more")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    KVS_FIELD_NUMBER: _ClassVar[int]
    MORE_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    kvs: _containers.RepeatedCompositeFieldContainer[_kv_pb2.KeyValue]
    more: bool
    count: int
    def __init__(
        self,
        header: ResponseHeader | _Mapping | None = ...,
        kvs: _Iterable[_kv_pb2.KeyValue | _Mapping] | None = ...,
        more: bool = ...,
        count: int | None = ...,
    ) -> None: ...

class PutRequest(_message.Message):
    __slots__ = ("ignore_lease", "ignore_value", "key", "lease", "prev_kv", "value")
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
    def __init__(
        self,
        key: bytes | None = ...,
        value: bytes | None = ...,
        lease: int | None = ...,
        prev_kv: bool = ...,
        ignore_value: bool = ...,
        ignore_lease: bool = ...,
    ) -> None: ...

class PutResponse(_message.Message):
    __slots__ = ("header", "prev_kv")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    PREV_KV_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    prev_kv: _kv_pb2.KeyValue
    def __init__(
        self,
        header: ResponseHeader | _Mapping | None = ...,
        prev_kv: _kv_pb2.KeyValue | _Mapping | None = ...,
    ) -> None: ...

class DeleteRangeRequest(_message.Message):
    __slots__ = ("key", "prev_kv", "range_end")
    KEY_FIELD_NUMBER: _ClassVar[int]
    RANGE_END_FIELD_NUMBER: _ClassVar[int]
    PREV_KV_FIELD_NUMBER: _ClassVar[int]
    key: bytes
    range_end: bytes
    prev_kv: bool
    def __init__(
        self, key: bytes | None = ..., range_end: bytes | None = ..., prev_kv: bool = ...
    ) -> None: ...

class DeleteRangeResponse(_message.Message):
    __slots__ = ("deleted", "header", "prev_kvs")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    DELETED_FIELD_NUMBER: _ClassVar[int]
    PREV_KVS_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    deleted: int
    prev_kvs: _containers.RepeatedCompositeFieldContainer[_kv_pb2.KeyValue]
    def __init__(
        self,
        header: ResponseHeader | _Mapping | None = ...,
        deleted: int | None = ...,
        prev_kvs: _Iterable[_kv_pb2.KeyValue | _Mapping] | None = ...,
    ) -> None: ...

class RequestOp(_message.Message):
    __slots__ = ("request_delete_range", "request_put", "request_range", "request_txn")
    REQUEST_RANGE_FIELD_NUMBER: _ClassVar[int]
    REQUEST_PUT_FIELD_NUMBER: _ClassVar[int]
    REQUEST_DELETE_RANGE_FIELD_NUMBER: _ClassVar[int]
    REQUEST_TXN_FIELD_NUMBER: _ClassVar[int]
    request_range: RangeRequest
    request_put: PutRequest
    request_delete_range: DeleteRangeRequest
    request_txn: TxnRequest
    def __init__(
        self,
        request_range: RangeRequest | _Mapping | None = ...,
        request_put: PutRequest | _Mapping | None = ...,
        request_delete_range: DeleteRangeRequest | _Mapping | None = ...,
        request_txn: TxnRequest | _Mapping | None = ...,
    ) -> None: ...

class ResponseOp(_message.Message):
    __slots__ = ("response_delete_range", "response_put", "response_range", "response_txn")
    RESPONSE_RANGE_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_PUT_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_DELETE_RANGE_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_TXN_FIELD_NUMBER: _ClassVar[int]
    response_range: RangeResponse
    response_put: PutResponse
    response_delete_range: DeleteRangeResponse
    response_txn: TxnResponse
    def __init__(
        self,
        response_range: RangeResponse | _Mapping | None = ...,
        response_put: PutResponse | _Mapping | None = ...,
        response_delete_range: DeleteRangeResponse | _Mapping | None = ...,
        response_txn: TxnResponse | _Mapping | None = ...,
    ) -> None: ...

class Compare(_message.Message):
    __slots__ = (
        "create_revision",
        "key",
        "mod_revision",
        "range_end",
        "result",
        "target",
        "value",
        "version",
    )
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
    def __init__(
        self,
        result: Compare.CompareResult | str | None = ...,
        target: Compare.CompareTarget | str | None = ...,
        key: bytes | None = ...,
        version: int | None = ...,
        create_revision: int | None = ...,
        mod_revision: int | None = ...,
        value: bytes | None = ...,
        range_end: bytes | None = ...,
    ) -> None: ...

class TxnRequest(_message.Message):
    __slots__ = ("compare", "failure", "success")
    COMPARE_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    FAILURE_FIELD_NUMBER: _ClassVar[int]
    compare: _containers.RepeatedCompositeFieldContainer[Compare]
    success: _containers.RepeatedCompositeFieldContainer[RequestOp]
    failure: _containers.RepeatedCompositeFieldContainer[RequestOp]
    def __init__(
        self,
        compare: _Iterable[Compare | _Mapping] | None = ...,
        success: _Iterable[RequestOp | _Mapping] | None = ...,
        failure: _Iterable[RequestOp | _Mapping] | None = ...,
    ) -> None: ...

class TxnResponse(_message.Message):
    __slots__ = ("header", "responses", "succeeded")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    SUCCEEDED_FIELD_NUMBER: _ClassVar[int]
    RESPONSES_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    succeeded: bool
    responses: _containers.RepeatedCompositeFieldContainer[ResponseOp]
    def __init__(
        self,
        header: ResponseHeader | _Mapping | None = ...,
        succeeded: bool = ...,
        responses: _Iterable[ResponseOp | _Mapping] | None = ...,
    ) -> None: ...

class CompactionRequest(_message.Message):
    __slots__ = ("physical", "revision")
    REVISION_FIELD_NUMBER: _ClassVar[int]
    PHYSICAL_FIELD_NUMBER: _ClassVar[int]
    revision: int
    physical: bool
    def __init__(self, revision: int | None = ..., physical: bool = ...) -> None: ...

class CompactionResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: ResponseHeader | _Mapping | None = ...) -> None: ...

class HashRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class HashResponse(_message.Message):
    __slots__ = ("hash", "header")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    HASH_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    hash: int
    def __init__(
        self, header: ResponseHeader | _Mapping | None = ..., hash: int | None = ...
    ) -> None: ...

class HashKVRequest(_message.Message):
    __slots__ = ("revision",)
    REVISION_FIELD_NUMBER: _ClassVar[int]
    revision: int
    def __init__(self, revision: int | None = ...) -> None: ...

class HashKVResponse(_message.Message):
    __slots__ = ("compact_revision", "hash", "header")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    HASH_FIELD_NUMBER: _ClassVar[int]
    COMPACT_REVISION_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    hash: int
    compact_revision: int
    def __init__(
        self,
        header: ResponseHeader | _Mapping | None = ...,
        hash: int | None = ...,
        compact_revision: int | None = ...,
    ) -> None: ...

class SnapshotRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class SnapshotResponse(_message.Message):
    __slots__ = ("blob", "header", "remaining_bytes")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    REMAINING_BYTES_FIELD_NUMBER: _ClassVar[int]
    BLOB_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    remaining_bytes: int
    blob: bytes
    def __init__(
        self,
        header: ResponseHeader | _Mapping | None = ...,
        remaining_bytes: int | None = ...,
        blob: bytes | None = ...,
    ) -> None: ...

class WatchRequest(_message.Message):
    __slots__ = ("cancel_request", "create_request")
    CREATE_REQUEST_FIELD_NUMBER: _ClassVar[int]
    CANCEL_REQUEST_FIELD_NUMBER: _ClassVar[int]
    create_request: WatchCreateRequest
    cancel_request: WatchCancelRequest
    def __init__(
        self,
        create_request: WatchCreateRequest | _Mapping | None = ...,
        cancel_request: WatchCancelRequest | _Mapping | None = ...,
    ) -> None: ...

class WatchCreateRequest(_message.Message):
    __slots__ = ("filters", "key", "prev_kv", "progress_notify", "range_end", "start_revision")
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
    def __init__(
        self,
        key: bytes | None = ...,
        range_end: bytes | None = ...,
        start_revision: int | None = ...,
        progress_notify: bool = ...,
        filters: _Iterable[WatchCreateRequest.FilterType | str] | None = ...,
        prev_kv: bool = ...,
    ) -> None: ...

class WatchCancelRequest(_message.Message):
    __slots__ = ("watch_id",)
    WATCH_ID_FIELD_NUMBER: _ClassVar[int]
    watch_id: int
    def __init__(self, watch_id: int | None = ...) -> None: ...

class WatchResponse(_message.Message):
    __slots__ = ("cancel_reason", "canceled", "compact_revision", "created", "events", "header", "watch_id")
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
    def __init__(
        self,
        header: ResponseHeader | _Mapping | None = ...,
        watch_id: int | None = ...,
        created: bool = ...,
        canceled: bool = ...,
        compact_revision: int | None = ...,
        cancel_reason: str | None = ...,
        events: _Iterable[_kv_pb2.Event | _Mapping] | None = ...,
    ) -> None: ...

class LeaseGrantRequest(_message.Message):
    __slots__ = ("ID", "TTL")
    TTL_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    TTL: int
    ID: int
    def __init__(self, TTL: int | None = ..., ID: int | None = ...) -> None: ...

class LeaseGrantResponse(_message.Message):
    __slots__ = ("ID", "TTL", "error", "header")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    TTL_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    ID: int
    TTL: int
    error: str
    def __init__(
        self,
        header: ResponseHeader | _Mapping | None = ...,
        ID: int | None = ...,
        TTL: int | None = ...,
        error: str | None = ...,
    ) -> None: ...

class LeaseRevokeRequest(_message.Message):
    __slots__ = ("ID",)
    ID_FIELD_NUMBER: _ClassVar[int]
    ID: int
    def __init__(self, ID: int | None = ...) -> None: ...

class LeaseRevokeResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: ResponseHeader | _Mapping | None = ...) -> None: ...

class LeaseKeepAliveRequest(_message.Message):
    __slots__ = ("ID",)
    ID_FIELD_NUMBER: _ClassVar[int]
    ID: int
    def __init__(self, ID: int | None = ...) -> None: ...

class LeaseKeepAliveResponse(_message.Message):
    __slots__ = ("ID", "TTL", "header")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    TTL_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    ID: int
    TTL: int
    def __init__(
        self,
        header: ResponseHeader | _Mapping | None = ...,
        ID: int | None = ...,
        TTL: int | None = ...,
    ) -> None: ...

class LeaseTimeToLiveRequest(_message.Message):
    __slots__ = ("ID", "keys")
    ID_FIELD_NUMBER: _ClassVar[int]
    KEYS_FIELD_NUMBER: _ClassVar[int]
    ID: int
    keys: bool
    def __init__(self, ID: int | None = ..., keys: bool = ...) -> None: ...

class LeaseTimeToLiveResponse(_message.Message):
    __slots__ = ("ID", "TTL", "grantedTTL", "header", "keys")
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
    def __init__(
        self,
        header: ResponseHeader | _Mapping | None = ...,
        ID: int | None = ...,
        TTL: int | None = ...,
        grantedTTL: int | None = ...,
        keys: _Iterable[bytes] | None = ...,
    ) -> None: ...

class Member(_message.Message):
    __slots__ = ("ID", "clientURLs", "name", "peerURLs")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    PEERURLS_FIELD_NUMBER: _ClassVar[int]
    CLIENTURLS_FIELD_NUMBER: _ClassVar[int]
    ID: int
    name: str
    peerURLs: _containers.RepeatedScalarFieldContainer[str]
    clientURLs: _containers.RepeatedScalarFieldContainer[str]
    def __init__(
        self,
        ID: int | None = ...,
        name: str | None = ...,
        peerURLs: _Iterable[str] | None = ...,
        clientURLs: _Iterable[str] | None = ...,
    ) -> None: ...

class MemberAddRequest(_message.Message):
    __slots__ = ("peerURLs",)
    PEERURLS_FIELD_NUMBER: _ClassVar[int]
    peerURLs: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, peerURLs: _Iterable[str] | None = ...) -> None: ...

class MemberAddResponse(_message.Message):
    __slots__ = ("header", "member", "members")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    MEMBER_FIELD_NUMBER: _ClassVar[int]
    MEMBERS_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    member: Member
    members: _containers.RepeatedCompositeFieldContainer[Member]
    def __init__(
        self,
        header: ResponseHeader | _Mapping | None = ...,
        member: Member | _Mapping | None = ...,
        members: _Iterable[Member | _Mapping] | None = ...,
    ) -> None: ...

class MemberRemoveRequest(_message.Message):
    __slots__ = ("ID",)
    ID_FIELD_NUMBER: _ClassVar[int]
    ID: int
    def __init__(self, ID: int | None = ...) -> None: ...

class MemberRemoveResponse(_message.Message):
    __slots__ = ("header", "members")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    MEMBERS_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    members: _containers.RepeatedCompositeFieldContainer[Member]
    def __init__(
        self,
        header: ResponseHeader | _Mapping | None = ...,
        members: _Iterable[Member | _Mapping] | None = ...,
    ) -> None: ...

class MemberUpdateRequest(_message.Message):
    __slots__ = ("ID", "peerURLs")
    ID_FIELD_NUMBER: _ClassVar[int]
    PEERURLS_FIELD_NUMBER: _ClassVar[int]
    ID: int
    peerURLs: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, ID: int | None = ..., peerURLs: _Iterable[str] | None = ...) -> None: ...

class MemberUpdateResponse(_message.Message):
    __slots__ = ("header", "members")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    MEMBERS_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    members: _containers.RepeatedCompositeFieldContainer[Member]
    def __init__(
        self,
        header: ResponseHeader | _Mapping | None = ...,
        members: _Iterable[Member | _Mapping] | None = ...,
    ) -> None: ...

class MemberListRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class MemberListResponse(_message.Message):
    __slots__ = ("header", "members")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    MEMBERS_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    members: _containers.RepeatedCompositeFieldContainer[Member]
    def __init__(
        self,
        header: ResponseHeader | _Mapping | None = ...,
        members: _Iterable[Member | _Mapping] | None = ...,
    ) -> None: ...

class DefragmentRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class DefragmentResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: ResponseHeader | _Mapping | None = ...) -> None: ...

class MoveLeaderRequest(_message.Message):
    __slots__ = ("targetID",)
    TARGETID_FIELD_NUMBER: _ClassVar[int]
    targetID: int
    def __init__(self, targetID: int | None = ...) -> None: ...

class MoveLeaderResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: ResponseHeader | _Mapping | None = ...) -> None: ...

class AlarmRequest(_message.Message):
    __slots__ = ("action", "alarm", "memberID")
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
    def __init__(
        self,
        action: AlarmRequest.AlarmAction | str | None = ...,
        memberID: int | None = ...,
        alarm: AlarmType | str | None = ...,
    ) -> None: ...

class AlarmMember(_message.Message):
    __slots__ = ("alarm", "memberID")
    MEMBERID_FIELD_NUMBER: _ClassVar[int]
    ALARM_FIELD_NUMBER: _ClassVar[int]
    memberID: int
    alarm: AlarmType
    def __init__(
        self, memberID: int | None = ..., alarm: AlarmType | str | None = ...
    ) -> None: ...

class AlarmResponse(_message.Message):
    __slots__ = ("alarms", "header")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    ALARMS_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    alarms: _containers.RepeatedCompositeFieldContainer[AlarmMember]
    def __init__(
        self,
        header: ResponseHeader | _Mapping | None = ...,
        alarms: _Iterable[AlarmMember | _Mapping] | None = ...,
    ) -> None: ...

class StatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class StatusResponse(_message.Message):
    __slots__ = ("dbSize", "header", "leader", "raftIndex", "raftTerm", "version")
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
    def __init__(
        self,
        header: ResponseHeader | _Mapping | None = ...,
        version: str | None = ...,
        dbSize: int | None = ...,
        leader: int | None = ...,
        raftIndex: int | None = ...,
        raftTerm: int | None = ...,
    ) -> None: ...

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
    def __init__(self, name: str | None = ..., password: str | None = ...) -> None: ...

class AuthUserAddRequest(_message.Message):
    __slots__ = ("name", "password")
    NAME_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    name: str
    password: str
    def __init__(self, name: str | None = ..., password: str | None = ...) -> None: ...

class AuthUserGetRequest(_message.Message):
    __slots__ = ("name",)
    NAME_FIELD_NUMBER: _ClassVar[int]
    name: str
    def __init__(self, name: str | None = ...) -> None: ...

class AuthUserDeleteRequest(_message.Message):
    __slots__ = ("name",)
    NAME_FIELD_NUMBER: _ClassVar[int]
    name: str
    def __init__(self, name: str | None = ...) -> None: ...

class AuthUserChangePasswordRequest(_message.Message):
    __slots__ = ("name", "password")
    NAME_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    name: str
    password: str
    def __init__(self, name: str | None = ..., password: str | None = ...) -> None: ...

class AuthUserGrantRoleRequest(_message.Message):
    __slots__ = ("role", "user")
    USER_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    user: str
    role: str
    def __init__(self, user: str | None = ..., role: str | None = ...) -> None: ...

class AuthUserRevokeRoleRequest(_message.Message):
    __slots__ = ("name", "role")
    NAME_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    name: str
    role: str
    def __init__(self, name: str | None = ..., role: str | None = ...) -> None: ...

class AuthRoleAddRequest(_message.Message):
    __slots__ = ("name",)
    NAME_FIELD_NUMBER: _ClassVar[int]
    name: str
    def __init__(self, name: str | None = ...) -> None: ...

class AuthRoleGetRequest(_message.Message):
    __slots__ = ("role",)
    ROLE_FIELD_NUMBER: _ClassVar[int]
    role: str
    def __init__(self, role: str | None = ...) -> None: ...

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
    def __init__(self, role: str | None = ...) -> None: ...

class AuthRoleGrantPermissionRequest(_message.Message):
    __slots__ = ("name", "perm")
    NAME_FIELD_NUMBER: _ClassVar[int]
    PERM_FIELD_NUMBER: _ClassVar[int]
    name: str
    perm: _auth_pb2.Permission
    def __init__(
        self, name: str | None = ..., perm: _auth_pb2.Permission | _Mapping | None = ...
    ) -> None: ...

class AuthRoleRevokePermissionRequest(_message.Message):
    __slots__ = ("key", "range_end", "role")
    ROLE_FIELD_NUMBER: _ClassVar[int]
    KEY_FIELD_NUMBER: _ClassVar[int]
    RANGE_END_FIELD_NUMBER: _ClassVar[int]
    role: str
    key: str
    range_end: str
    def __init__(
        self, role: str | None = ..., key: str | None = ..., range_end: str | None = ...
    ) -> None: ...

class AuthEnableResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: ResponseHeader | _Mapping | None = ...) -> None: ...

class AuthDisableResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: ResponseHeader | _Mapping | None = ...) -> None: ...

class AuthenticateResponse(_message.Message):
    __slots__ = ("header", "token")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    token: str
    def __init__(
        self, header: ResponseHeader | _Mapping | None = ..., token: str | None = ...
    ) -> None: ...

class AuthUserAddResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: ResponseHeader | _Mapping | None = ...) -> None: ...

class AuthUserGetResponse(_message.Message):
    __slots__ = ("header", "roles")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    ROLES_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    roles: _containers.RepeatedScalarFieldContainer[str]
    def __init__(
        self,
        header: ResponseHeader | _Mapping | None = ...,
        roles: _Iterable[str] | None = ...,
    ) -> None: ...

class AuthUserDeleteResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: ResponseHeader | _Mapping | None = ...) -> None: ...

class AuthUserChangePasswordResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: ResponseHeader | _Mapping | None = ...) -> None: ...

class AuthUserGrantRoleResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: ResponseHeader | _Mapping | None = ...) -> None: ...

class AuthUserRevokeRoleResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: ResponseHeader | _Mapping | None = ...) -> None: ...

class AuthRoleAddResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: ResponseHeader | _Mapping | None = ...) -> None: ...

class AuthRoleGetResponse(_message.Message):
    __slots__ = ("header", "perm")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    PERM_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    perm: _containers.RepeatedCompositeFieldContainer[_auth_pb2.Permission]
    def __init__(
        self,
        header: ResponseHeader | _Mapping | None = ...,
        perm: _Iterable[_auth_pb2.Permission | _Mapping] | None = ...,
    ) -> None: ...

class AuthRoleListResponse(_message.Message):
    __slots__ = ("header", "roles")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    ROLES_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    roles: _containers.RepeatedScalarFieldContainer[str]
    def __init__(
        self,
        header: ResponseHeader | _Mapping | None = ...,
        roles: _Iterable[str] | None = ...,
    ) -> None: ...

class AuthUserListResponse(_message.Message):
    __slots__ = ("header", "users")
    HEADER_FIELD_NUMBER: _ClassVar[int]
    USERS_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    users: _containers.RepeatedScalarFieldContainer[str]
    def __init__(
        self,
        header: ResponseHeader | _Mapping | None = ...,
        users: _Iterable[str] | None = ...,
    ) -> None: ...

class AuthRoleDeleteResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: ResponseHeader | _Mapping | None = ...) -> None: ...

class AuthRoleGrantPermissionResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: ResponseHeader | _Mapping | None = ...) -> None: ...

class AuthRoleRevokePermissionResponse(_message.Message):
    __slots__ = ("header",)
    HEADER_FIELD_NUMBER: _ClassVar[int]
    header: ResponseHeader
    def __init__(self, header: ResponseHeader | _Mapping | None = ...) -> None: ...
