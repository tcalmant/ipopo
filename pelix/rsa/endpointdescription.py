#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

EndpointDescription class API

:author: Scott Lewis
:copyright: Copyright 2020, Scott Lewis
:license: Apache License 2.0
:version: 3.1.0

..

    Copyright 2020 Scott Lewis

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        https://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

from typing import Any, Dict, Iterable, List, Optional, Tuple, Union, cast

from pelix.constants import FRAMEWORK_UID, OBJECTCLASS, SERVICE_ID
from pelix.internals.registry import ServiceReference
from pelix.ldapfilter import LdapFilterOrCriteria, get_ldap_filter
from pelix.rsa import (
    ECF_ASYNC_INTERFACE_SUFFIX,
    ECF_ENDPOINT_CONNECTTARGET_ID,
    ECF_ENDPOINT_CONTAINERID_NAMESPACE,
    ECF_ENDPOINT_ID,
    ECF_ENDPOINT_IDFILTER_IDS,
    ECF_ENDPOINT_REMOTESERVICE_FILTER,
    ECF_ENDPOINT_TIMESTAMP,
    ECF_RSVC_ID,
    ECF_SERVICE_ASYNC_RSPROXY_CLASS_,
    ECF_SERVICE_EXPORTED_ASYNC_INTERFACES,
    ECF_SERVICE_EXPORTED_ASYNC_NOPROXY,
    ENDPOINT_FRAMEWORK_UUID,
    ENDPOINT_ID,
    ENDPOINT_PACKAGE_VERSION_,
    ENDPOINT_SERVICE_ID,
    OSGI_BASIC_TIMEOUT_INTENT,
    REMOTE_CONFIGS_SUPPORTED,
    REMOTE_INTENTS_SUPPORTED,
    SERVICE_IMPORTED,
    SERVICE_IMPORTED_CONFIGS,
    SERVICE_INTENTS,
    get_matching_interfaces,
    get_prop_value,
    get_string_plus_property,
    get_string_plus_property_value,
    is_reserved_property,
    merge_dicts,
    rsid_to_string,
    set_prop_if_null,
)

# ------------------------------------------------------------------------------
# Module version

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


def encode_list(key: str, list_: Iterable[Any]) -> Dict[str, str]:
    """
    Converts a list into a space-separated string and puts it in a dictionary

    :param key: Dictionary key to store the list
    :param list_: A list of objects
    :return: A dictionary key->string or an empty dictionary
    """
    if not list_:
        return {}
    return {key: " ".join(str(i) for i in list_)}


def package_name(package: str) -> str:
    """
    Returns the package name of the given module name
    """
    if not package:
        return ""

    lastdot = package.rfind(".")
    if lastdot == -1:
        return package

    return package[:lastdot]


def encode_osgi_props(ed: "EndpointDescription") -> Dict[str, str]:
    """
    Prepares a dictionary of OSGi properties for the given EndpointDescription
    """
    result_props = {}
    intfs = ed.get_interfaces()
    result_props[OBJECTCLASS] = " ".join(intfs)
    for intf in intfs:
        pkg_name = package_name(intf)
        ver = ed.get_package_version(pkg_name)
        if ver and not ver == (0, 0, 0):
            result_props[ENDPOINT_PACKAGE_VERSION_] = ".".join(str(v) for v in ver)

    result_props[ENDPOINT_ID] = ed.get_id()
    result_props[ENDPOINT_SERVICE_ID] = str(ed.get_service_id())
    result_props[ENDPOINT_FRAMEWORK_UUID] = ed.get_framework_uuid()
    imp_configs = ed.get_imported_configs()
    if imp_configs:
        result_props[SERVICE_IMPORTED_CONFIGS] = " ".join(ed.get_imported_configs())
    intents = ed.get_intents()
    if intents:
        result_props[SERVICE_INTENTS] = " ".join(intents)
    remote_configs = ed.get_remote_configs_supported()
    if remote_configs:
        result_props[REMOTE_CONFIGS_SUPPORTED] = " ".join(remote_configs)
    remote_intents = ed.get_remote_intents_supported()
    if remote_intents:
        result_props[REMOTE_INTENTS_SUPPORTED] = " ".join(remote_intents)
    return result_props


def decode_list(input_props: Dict[str, str], name: str) -> List[str]:
    """
    Decodes a space-separated list
    """
    val_str = input_props.get(name, None)
    if val_str:
        return val_str.split(" ")
    return []


def decode_osgi_props(input_props: Dict[str, Any]) -> Dict[str, Any]:
    """
    Decodes the OSGi properties of the given endpoint properties
    """
    result_props = {}
    intfs = decode_list(input_props, OBJECTCLASS)
    result_props[OBJECTCLASS] = intfs
    for intf in intfs:
        package_key = ENDPOINT_PACKAGE_VERSION_ + package_name(intf)
        intfversionstr = input_props.get(package_key, None)
        if intfversionstr:
            result_props[package_key] = intfversionstr
    result_props[ENDPOINT_ID] = input_props[ENDPOINT_ID]
    result_props[ENDPOINT_SERVICE_ID] = input_props[ENDPOINT_SERVICE_ID]
    result_props[ENDPOINT_FRAMEWORK_UUID] = input_props[ENDPOINT_FRAMEWORK_UUID]
    imp_configs = decode_list(input_props, SERVICE_IMPORTED_CONFIGS)
    if imp_configs:
        result_props[SERVICE_IMPORTED_CONFIGS] = imp_configs
    intents = decode_list(input_props, SERVICE_INTENTS)
    if intents:
        result_props[SERVICE_INTENTS] = intents
    remote_configs = decode_list(input_props, REMOTE_CONFIGS_SUPPORTED)
    if remote_configs:
        result_props[REMOTE_CONFIGS_SUPPORTED] = remote_configs
    remote_intents = decode_list(input_props, REMOTE_INTENTS_SUPPORTED)
    if remote_intents:
        result_props[REMOTE_INTENTS_SUPPORTED] = remote_intents
    return result_props


def decode_endpoint_props(input_props: Dict[str, Any]) -> Dict[str, Any]:
    """
    Decodes the endpoint properties from the given dictionary
    """
    ed_props = decode_osgi_props(input_props)
    ed_props[ECF_ENDPOINT_CONTAINERID_NAMESPACE] = input_props[ECF_ENDPOINT_CONTAINERID_NAMESPACE]
    ed_props[ECF_RSVC_ID] = int(input_props[ECF_RSVC_ID])
    ed_props[ECF_ENDPOINT_ID] = input_props[ECF_ENDPOINT_ID]
    ed_props[ECF_ENDPOINT_TIMESTAMP] = int(input_props[ECF_ENDPOINT_TIMESTAMP])
    target_id = input_props.get(ECF_ENDPOINT_CONNECTTARGET_ID, None)
    if target_id:
        ed_props[ECF_ENDPOINT_CONNECTTARGET_ID] = target_id
    id_filters = decode_list(input_props, ECF_ENDPOINT_IDFILTER_IDS)
    if id_filters:
        ed_props[ECF_ENDPOINT_IDFILTER_IDS] = id_filters
    rs_filter = input_props.get(ECF_ENDPOINT_REMOTESERVICE_FILTER, None)
    if rs_filter:
        ed_props[ECF_ENDPOINT_REMOTESERVICE_FILTER] = rs_filter
    async_intfs = input_props.get(ECF_SERVICE_EXPORTED_ASYNC_INTERFACES, None)
    if async_intfs:
        if async_intfs == "*":
            ed_props[ECF_SERVICE_EXPORTED_ASYNC_INTERFACES] = async_intfs
        else:
            async_intfs = decode_list(input_props, ECF_SERVICE_EXPORTED_ASYNC_INTERFACES)
            if async_intfs:
                ed_props[ECF_SERVICE_EXPORTED_ASYNC_INTERFACES] = async_intfs

    for key in input_props.keys():
        if not is_reserved_property(key):
            val = input_props.get(key, None)
            if val:
                ed_props[key] = val
    return ed_props


def encode_endpoint_props(ed: "EndpointDescription") -> Dict[str, Any]:
    """
    Encodes the properties of the given EndpointDescription
    """
    props: Dict[str, Any] = encode_osgi_props(ed)
    props[ECF_RSVC_ID] = str(ed.get_remoteservice_id()[1])
    props[ECF_ENDPOINT_ID] = str(ed.get_container_id()[1])
    props[ECF_ENDPOINT_CONTAINERID_NAMESPACE] = str(ed.get_container_id()[0])
    props[ECF_ENDPOINT_TIMESTAMP] = str(ed.get_timestamp())
    ctid = ed.get_connect_target_id()
    if ctid:
        props[ECF_ENDPOINT_CONNECTTARGET_ID] = str(ctid)
    id_filters = ed.get_id_filters()
    if id_filters:
        props[ECF_ENDPOINT_IDFILTER_IDS] = " ".join([x[1] for x in id_filters])
    rs_filter = ed.get_remoteservice_filter()
    if rs_filter:
        props[ECF_ENDPOINT_REMOTESERVICE_FILTER] = ed.get_remoteservice_filter()
    async_intfs = ed.get_async_interfaces()
    if async_intfs:
        props[ECF_SERVICE_EXPORTED_ASYNC_INTERFACES] = " ".join(async_intfs)

    all_props = ed.get_properties()
    other_props = {
        key: str(value) if value is not None else None
        for key, value in all_props.items()
        if not is_reserved_property(key)
    }
    return merge_dicts(props, other_props)


# ------------------------------------------------------------------------------
# EndpointDescription class
# ------------------------------------------------------------------------------


class EndpointDescription:
    """
    Description of an RSA Endpoint
    """

    @classmethod
    def fromsvcref(cls, svc_ref: ServiceReference[Any]) -> "EndpointDescription":
        return cls(svc_ref, None)

    @classmethod
    def fromprops(cls, props: Dict[str, Any]) -> "EndpointDescription":
        return cls(None, props)

    @classmethod
    def fromsvcrefprops(cls, svc_ref: ServiceReference[Any], props: Dict[str, Any]) -> "EndpointDescription":
        return cls(svc_ref, props)

    @classmethod
    def _condition_props(cls, properties: Dict[str, Any]) -> Dict[str, Any]:
        set_prop_if_null(SERVICE_IMPORTED, properties, True)
        for key in properties.keys():
            if key.startswith("services.exported."):
                del properties[key]
        return properties

    @classmethod
    def _verify_export_props(
        cls, svc_ref: ServiceReference[Any], all_properties: Dict[str, Any]
    ) -> Dict[str, Any]:
        props = all_properties.copy()
        set_prop_if_null(ENDPOINT_SERVICE_ID, props, svc_ref.get_property(SERVICE_ID))
        set_prop_if_null(ENDPOINT_FRAMEWORK_UUID, props, svc_ref.get_property(FRAMEWORK_UID))
        return props

    def __init__(
        self, svc_ref: Optional[ServiceReference[Any]] = None, properties: Optional[Dict[str, Any]] = None
    ) -> None:
        if svc_ref is None and properties is None:
            raise ValueError("Either service reference or properties argument must be " "non-null")

        all_properties: Dict[str, Any] = {}

        if svc_ref is not None:
            all_properties.update(svc_ref.get_properties())

        if properties is not None:
            all_properties.update(properties)

        if svc_ref is not None:
            self._properties = EndpointDescription._verify_export_props(svc_ref, all_properties)
        else:
            self._properties = all_properties

        self._interfaces = cast(List[str], (self._properties.get(OBJECTCLASS) or [])[:])
        self._service_id = self._verify_long_prop(ENDPOINT_SERVICE_ID)
        self._framework_uuid = self._verify_str_prop(ENDPOINT_FRAMEWORK_UUID)
        endpoint_id = self._verify_str_prop(ENDPOINT_ID)
        if endpoint_id is None:
            raise ValueError("endpoint.id property must be set")
        self._id = endpoint_id.strip()

        if not self.get_configuration_types():
            raise ValueError("service.imported.configs property must be set and non-empty")

        self._ecfid = self._verify_str_prop(ECF_ENDPOINT_ID)
        if self._ecfid is None:
            raise ValueError("ecf.endpoint.id must not be null")
        self._timestamp = self._verify_long_prop(ECF_ENDPOINT_TIMESTAMP)
        if self._timestamp == 0:
            self._timestamp = self.get_service_id()
        self._id_namespace = self._verify_str_prop(ECF_ENDPOINT_CONTAINERID_NAMESPACE)
        self._container_id = (self._id_namespace, self._ecfid)
        self._rs_id = self._verify_long_prop(ECF_RSVC_ID)
        if self._rs_id is None:
            self._rs_id = self.get_service_id()

        connect_target_name = cast(Optional[str], self._get_prop(ECF_ENDPOINT_CONNECTTARGET_ID))

        self._connect_target_id: Optional[Tuple[str, str]] = None
        if connect_target_name is not None:
            self._connect_target_id = (self._id_namespace, connect_target_name)

        id_filter_names = self._get_string_plus_property(ECF_ENDPOINT_IDFILTER_IDS)

        self._id_filters: Optional[List[Tuple[str, str]]] = None
        if id_filter_names:
            self._id_filters = [(self._id_namespace, x) for x in id_filter_names]

        self._rs_filter = cast(Optional[str], self._get_prop(ECF_ENDPOINT_REMOTESERVICE_FILTER))
        self._async_intfs = self._verify_async_intfs()

    def __hash__(self) -> int:
        return hash(self._id)

    def __eq__(self, other: Any) -> Any:
        return isinstance(other, EndpointDescription) and self._id == other._id

    def __ne__(self, other: Any) -> Any:
        return not isinstance(other, EndpointDescription) or self._id != other._id

    def __str__(self) -> str:
        get_remoteservice_id = self.get_remoteservice_id()
        return (
            "EndpointDescription(id={0}; endpoint.service.id={1}; "
            "framework.uuid={2}; ecf.endpoint.id={3}:{4})".format(
                self.get_id(),
                self.get_service_id(),
                self.get_framework_uuid(),
                get_remoteservice_id[0],
                get_remoteservice_id[1],
            )
        )

    def _get_prop(self, key: str, default: Any = None) -> Any:
        return get_prop_value(key, self._properties, default)

    def _get_string_plus_property(self, key: str) -> List[str]:
        return get_string_plus_property(key, self._properties) or []

    def _verify_long_prop(self, prop: str) -> int:
        value = self._get_prop(prop)
        return int(value) if value else int(0)

    def _verify_str_prop(self, prop: str) -> str:
        value = self._get_prop(prop)
        if value is None:
            raise ValueError(f"prop name={prop} must be present in properties")
        return str(value)

    def _convert_intf_to_async(self, intf: str) -> str:
        async_proxy_intf = cast(str, self._get_prop(ECF_SERVICE_ASYNC_RSPROXY_CLASS_))
        if async_proxy_intf is not None:
            return async_proxy_intf

        if intf.endswith(ECF_ASYNC_INTERFACE_SUFFIX):
            return intf

        return intf + ECF_ASYNC_INTERFACE_SUFFIX

    def _verify_async_intfs(self) -> List[str]:
        matching: Optional[List[str]] = []
        no_async_prop = self._get_prop(ECF_SERVICE_EXPORTED_ASYNC_NOPROXY)
        if no_async_prop is None:
            async_inf_val = self._get_prop(ECF_SERVICE_EXPORTED_ASYNC_INTERFACES)
            if async_inf_val is not None:
                matching = get_matching_interfaces(self.get_interfaces(), async_inf_val)
        return [self._convert_intf_to_async(x) for x in matching or []]

    def get_container_id(self) -> Tuple[str, str]:
        return self._container_id

    def get_connect_target_id(self) -> Optional[Tuple[str, str]]:
        return self._connect_target_id

    def get_timestamp(self) -> int:
        return self._timestamp

    def get_remoteservice_id(self) -> Tuple[Tuple[str, str], int]:
        return (self.get_container_id(), self._rs_id)

    def get_remoteservice_idstr(self) -> str:
        return rsid_to_string(self.get_remoteservice_id())

    def get_id_filters(self) -> Optional[List[Tuple[str, str]]]:
        return self._id_filters

    def get_remoteservice_filter(self) -> Optional[str]:
        return self._rs_filter

    def get_async_interfaces(self) -> List[str]:
        return self._async_intfs

    def get_framework_uuid(self) -> str:
        return self._framework_uuid

    def get_osgi_basic_timeout(self) -> Optional[int]:
        timeout = self.get_properties().get(OSGI_BASIC_TIMEOUT_INTENT, None)
        if isinstance(timeout, str):
            timeout = int(timeout)
        return int(timeout / 1000) if timeout else None

    def get_id(self) -> str:
        """
        Returns the endpoint's id.

        :return: str
        """
        return self._id

    def get_remote_intents_supported(self) -> List[str]:
        return self._get_string_plus_property(REMOTE_INTENTS_SUPPORTED)

    def get_intents(self) -> List[str]:
        """
        Returns the list of intents required by this endpoint.

        The intents are based on the service.intents on an imported service,
        except for any intents that are additionally provided by the importing
        distribution provider.
        All qualified intents must have been expanded.
        This value of the intents is stored in the
        rsa.SERVICE_INTENTS service property.

        :return: A list of intents (list of str)
        """
        # Return a copy of the list
        return self._get_string_plus_property(SERVICE_INTENTS)

    def get_interfaces(self) -> List[str]:
        """
        Provides the list of interfaces implemented by the exported service.

        :return: A list of specifications (list of str)
        """
        return self._interfaces

    def get_imported_configs(self) -> List[str]:
        return self.get_configuration_types()

    def update_imported_configs(self, imported_configs: Any) -> None:
        self._properties[SERVICE_IMPORTED_CONFIGS] = get_string_plus_property_value(imported_configs)

    def get_configuration_types(self) -> List[str]:
        return self._get_string_plus_property(SERVICE_IMPORTED_CONFIGS)

    def get_remote_configs_supported(self) -> List[str]:
        return self._get_string_plus_property(REMOTE_CONFIGS_SUPPORTED)

    def get_service_id(self) -> int:
        return self._service_id

    def get_package_version(self, package: str) -> Tuple[int, ...]:
        """
        Provides the version of the given package name.

        :param package: The name of the package
        :return: The version of the specified package as a tuple or (0,0,0)
        """
        name = f"{ENDPOINT_PACKAGE_VERSION_}{package}"
        try:
            # Get the version string
            version = self._properties[name]
            # Split dots ('.')
            return tuple(int(i) for i in version.split("."))
        except (KeyError, ValueError):
            # No version
            return 0, 0, 0

    def get_properties(self) -> Dict[str, Any]:
        """
        Returns all endpoint properties.

        :return: A copy of the endpoint properties
        """
        return self._properties.copy()

    def is_same_service(self, endpoint: "EndpointDescription") -> bool:
        """
        Tests if this endpoint and the given one have the same framework UUID
        and service ID

        :param endpoint: Another endpoint
        :return: True if both endpoints represent the same remote service
        """
        return (
            self.get_framework_uuid() == endpoint.get_framework_uuid()
            and self.get_service_id() == endpoint.get_service_id()
        )

    def matches(self, ldap_filter: Union[None, str, LdapFilterOrCriteria]) -> bool:
        """
        Tests the properties of this EndpointDescription against the given
        filter

        :param ldap_filter: A filter
        :return: True if properties matches the filter
        """
        parsed_filter = get_ldap_filter(ldap_filter)
        if parsed_filter is not None:
            return parsed_filter.matches(self._properties)
        return True
