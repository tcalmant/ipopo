#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Remote Service Admin Shell Commands

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

import os
from threading import RLock
from traceback import print_exception
from typing import Any, List, Optional, Set, Tuple, TypeVar, cast

import pelix.rsa.remoteserviceadmin as rsa_impl
from pelix.constants import SERVICE_ID
from pelix.framework import BundleContext
from pelix.internals.registry import ServiceReference
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Instantiate,
    Invalidate,
    Property,
    Provides,
    Requires,
    UnbindField,
    Validate,
)
from pelix.rsa import (
    SERVICE_EXPORTED_CONFIGS,
    SERVICE_EXPORTED_INTERFACES,
    ExportRegistration,
    ImportRegistration,
    RemoteServiceAdmin,
    RemoteServiceAdminEvent,
    prop_dot_suffix,
)
from pelix.rsa.edef import EDEFReader, EDEFWriter
from pelix.rsa.endpointdescription import EndpointDescription
from pelix.rsa.providers.distribution import (
    SERVICE_EXPORT_CONTAINER,
    SERVICE_IMPORT_CONTAINER,
    Container,
    DistributionProvider,
    ExportDistributionProvider,
    ImportDistributionProvider,
)
from pelix.shell import ShellCommandMethod, ShellCommandsProvider, ShellUtils
from pelix.shell.beans import ShellSession

# ------------------------------------------------------------------------------
# Module version

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

T = TypeVar("T")

# ------------------------------------------------------------------------------


def _full_class_name(obj: Any) -> str:
    """
    Returns the full name of the class of the given object

    :param obj: Any Python object
    :return: The full name of the class of the object (if possible)
    """
    module = obj.__class__.__module__
    if module is None or module == str.__class__.__module__:
        return str(obj.__class__.__name__)
    return f"{module}.{obj.__class__.__name__}"


RSA_COMMAND_NAME_PROP = "rsa.command"
RSA_COMMAND_FILENAME_PROP = "edeffilename"
RSA_COMMAND_EXPORT_CONFIG_PROP = "defaultexportconfig"

# ------------------------------------------------------------------------------


@ComponentFactory("rsa-command-factory")
@Requires("_utils", ShellUtils)
@Requires("_rsa", RemoteServiceAdmin)
@Requires("_imp_containers", SERVICE_IMPORT_CONTAINER, True, True)
@Requires("_exp_containers", SERVICE_EXPORT_CONTAINER, True, True)
@Requires("_imp_dist_providers", ImportDistributionProvider, True, True)
@Requires("_exp_dist_providers", ExportDistributionProvider, True, True)
@Provides(ShellCommandsProvider)
@Property(
    "_edef_filename",
    prop_dot_suffix(RSA_COMMAND_NAME_PROP, RSA_COMMAND_FILENAME_PROP),
    "edef.xml",
)
@Property(
    "_export_config",
    prop_dot_suffix(RSA_COMMAND_NAME_PROP, RSA_COMMAND_EXPORT_CONFIG_PROP),
    "ecf.xmlrpc.server",
)
@Instantiate("rsa-command")
class RSACommandHandler(ShellCommandsProvider):
    """
    RSA implementation of command handler service...e.g. SERVICE_SHELL_COMMAND
    Exposes a number of shell commands for RSA operations...e.g. exportservice
    importservice, listconfigs, listproviders, listcontainers, etc
    """

    SHELL_NAMESPACE = "rsa"
    CONTAINER_FORMAT = (
        "ID={0}\n\tNamespace={1}\n\tClass={2}\n\tConnectedTo={3}\n"
        "\tConnectNamespace={4}\n\tConfig Type/Distribution Provider={5}"
    )
    PROVIDER_FORMAT = "ID={0}\n\tSupported Configs={1}\n\tSupportedIntents={2}"

    _utils: ShellUtils
    _rsa: RemoteServiceAdmin
    _imp_dist_providers: List[ImportDistributionProvider]
    _exp_dist_providers: List[ExportDistributionProvider]

    def __init__(self) -> None:
        self._context: Optional[BundleContext] = None
        self._imp_containers: List[Container] = []
        self._exp_containers: List[Container] = []
        self._edef_filename: str = "edef.xml"
        self._export_config: str = "ecf.xmlrpc.server"
        self._bind_lock = RLock()

    def _bind_lists(self, field: List[T], service: T) -> None:
        """
        Thread-safe handling of addition in a list of bound services

        :param field: Name of the injected field
        :param service: Injected service
        """
        with self._bind_lock:
            field.append(service)

    def _unbind_lists(self, field: List[T], service: T) -> None:
        """
        Thread-safe handling of removal in a list of bound services

        :param field: Name of the injected field
        :param service: Removed service
        """
        with self._bind_lock:
            try:
                field.remove(service)
            except ValueError:
                pass

    @BindField("_imp_containers")
    def _bind_imp_containers(
        self, field: str, service: Container, service_ref: ServiceReference[Container]
    ) -> None:
        self._bind_lists(self._imp_containers, service)

    @UnbindField("_imp_containers")
    def _unbind_imp_containers(
        self, field: str, service: Container, service_ref: ServiceReference[Container]
    ) -> None:
        self._unbind_lists(self._imp_containers, service)

    @BindField("_exp_containers")
    def _bind_exp_containers(
        self, field: str, service: Container, service_ref: ServiceReference[Container]
    ) -> None:
        self._bind_lists(self._exp_containers, service)

    @UnbindField("_exp_containers")
    def _unbind_exp_containers(
        self, field: str, service: Container, service_ref: ServiceReference[Container]
    ) -> None:
        self._unbind_lists(self._exp_containers, service)

    @BindField("_imp_dist_providers")
    def _bind_imp_dist_providers(
        self,
        field: str,
        service: ImportDistributionProvider,
        service_ref: ServiceReference[ImportDistributionProvider],
    ) -> None:
        self._bind_lists(self._imp_dist_providers, service)

    @UnbindField("_imp_dist_providers")
    def _unbind_imp_dist_providers(
        self,
        field: str,
        service: ImportDistributionProvider,
        service_ref: ServiceReference[ImportDistributionProvider],
    ) -> None:
        self._unbind_lists(self._imp_dist_providers, service)

    @BindField("_exp_dist_providers")
    def _bind_exp_dist_providers(
        self,
        field: str,
        service: ExportDistributionProvider,
        service_ref: ServiceReference[ExportDistributionProvider],
    ) -> None:
        self._bind_lists(self._exp_dist_providers, service)

    @UnbindField("_exp_dist_providers")
    def _unbind_exp_dist_providers(
        self,
        field: str,
        service: ExportDistributionProvider,
        service_ref: ServiceReference[ExportDistributionProvider],
    ) -> None:
        self._unbind_lists(self._exp_dist_providers, service)

    def _get_containers(self, container_id: Optional[str] = None) -> List[Container]:
        """
        Gets the list of import and export containers

        :param container_id: An optional container ID
        :return: All containers or those matching the given ID
        """
        with self._bind_lock:
            containers = set(self._imp_containers + self._exp_containers)
            if container_id:
                return [c for c in containers if c.get_id() == container_id]

            return list(containers)

    def _get_dist_providers(self, provider_id: Optional[str] = None) -> List[DistributionProvider]:
        """
        Gets the list of import and export providers

        :param provider_id: An optional provider ID
        :return: All providers or those matching the given ID
        """
        with self._bind_lock:
            providers: Set[DistributionProvider] = set(self._imp_dist_providers)
            providers.update(self._exp_dist_providers)
            if provider_id:
                return [p for p in providers if p.get_config_name() == provider_id]

            return list(providers)

    @Validate
    def _validate(self, bundle_context: BundleContext) -> None:
        """
        Component validated
        """
        self._context = bundle_context

    @Invalidate
    def _invalidate(self, _: BundleContext) -> None:
        """
        Component invalidated
        """
        if self._edef_filename and os.path.isfile(self._edef_filename):
            os.remove(self._edef_filename)

    @staticmethod
    def get_namespace() -> str:
        """
        Returns the namespace of the shell commands
        """
        return RSACommandHandler.SHELL_NAMESPACE

    def get_methods(self) -> List[Tuple[str, ShellCommandMethod]]:
        """
        Returns the commands provided by this service
        """
        return [
            ("listconfigs", self._list_providers),
            ("lcfgs", self._list_providers),
            ("listproviders", self._list_providers),
            ("listcontainers", self._list_containers),
            ("lcs", self._list_containers),
            ("listexports", self._list_exported_configs),
            ("listimports", self._list_imported_configs),
            ("lexps", self._list_exported_configs),
            ("limps", self._list_imported_configs),
            ("importservice", self._import_edef),
            ("impsvc", self._import_edef),
            ("exportservice", self._export_service),
            ("exportsvc", self._export_service),
            ("unimportservice", self._unimport),
            ("unimpsvc", self._unimport),
            ("unexportservice", self._unexport),
            ("unexpsvc", self._unexport),
            ("showdefaults", self._show_defaults),
            ("setdefaults", self._set_defaults),
            ("showedeffile", self._show_edef),
        ]

    def remote_admin_event(self, event: RemoteServiceAdminEvent) -> None:
        """
        Handle a remote service admin event
        """
        if event.get_type() == RemoteServiceAdminEvent.EXPORT_REGISTRATION:
            ed = event.get_description()
            if ed is not None:
                EDEFWriter().write([ed], self._edef_filename)

    def _show_defaults(self, io_handler: ShellSession) -> None:
        """
        Show default edeffile and default export_config
        """
        io_handler.write_line(
            "Defaults\n\texport_config={0}\n\tEDEF file={1};exists={2}",
            self._export_config,
            self._edef_filename,
            os.path.isfile(self._edef_filename),
        )

    def _set_defaults(
        self, io_handler: ShellSession, export_config: str, edef_file: Optional[str] = None
    ) -> None:
        """
        Set the export_config and optionally the edef_file default values
        """
        self._export_config = export_config
        if edef_file:
            self._edef_filename = edef_file
        self._show_defaults(io_handler)

    def _show_edef(self, io_handler: ShellSession) -> None:
        """
        Show contents of EDEF file
        """
        if not os.path.isfile(self._edef_filename):
            io_handler.write_line("EDEF file '{0}' does not exist!", self._edef_filename)
        else:
            with open(self._edef_filename, "r") as f:
                eds = EDEFReader().parse(f.read())

            io_handler.write_line(EDEFWriter().to_string(eds))

    def _list_providers(self, io_handler: ShellSession, provider_id: Optional[str] = None) -> None:
        """
        List export/import providers. If <provider_id> given,
        details on that provider
        """
        with self._bind_lock:
            providers = self._get_dist_providers(provider_id)

        if providers:
            if provider_id:
                provider = providers[0]
                io_handler.write_line(
                    self.PROVIDER_FORMAT.format(
                        provider.get_config_name(),
                        provider.get_supported_configs(),
                        provider.get_supported_intents(),
                    )
                )
            else:
                title = ("Distribution Provider/Config", "Class")
                rows = [(p.get_config_name(), _full_class_name(p)) for p in providers]
                io_handler.write_line(self._utils.make_table(title, rows))

    def _list_containers(self, io_handler: ShellSession, container_id: Optional[str] = None) -> None:
        """
        List existing import/export containers.
        If <container_id> given, details on that container
        """
        with self._bind_lock:
            containers = self._get_containers(container_id)
        if containers:
            if container_id:
                container = containers[0]
                connected_id = container.get_connected_id()
                ns = container.get_namespace()
                io_handler.write_line(
                    self.CONTAINER_FORMAT.format(
                        container.get_id(),
                        ns,
                        _full_class_name(container),
                        connected_id,
                        ns,
                        container.get_config_name(),
                    )
                )
            else:
                title = ("Container ID/instance.name", "Class")
                rows = [(c.get_id(), _full_class_name(c)) for c in containers]
                io_handler.write_line(self._utils.make_table(title, rows))

    def _list_imports(
        self, session: ShellSession, import_regs: List[ImportRegistration], endpoint_id: Optional[str] = None
    ) -> None:
        """
        Lists the imported services
        """
        if endpoint_id:
            matching_eds = [
                ed
                for ed in (x.get_description() for x in import_regs)
                if ed is not None and ed.get_id() == endpoint_id
            ]
            if matching_eds:
                session.write_line("Endpoint description for endpoint.id={0}:", endpoint_id)
                session.write_line(EDEFWriter().to_string(matching_eds))
        else:
            title = (
                "Endpoint ID",
                "Container ID",
                "Local Service ID",
                "Remote Service ID",
            )
            rows = []
            for import_reg in import_regs:
                ed = import_reg.get_description()
                svc_ref = import_reg.get_reference()
                if ed is None or svc_ref is None:
                    session.write_line("Invalid import registration found: {0}", import_reg)
                    continue

                rows.append(
                    (
                        ed.get_id(),
                        ed.get_container_id()[1],
                        svc_ref.get_property(SERVICE_ID),
                        ed.get_service_id(),
                    )
                )

            session.write_line(self._utils.make_table(title, rows))

    def _list_exports(
        self, session: ShellSession, configs: List[ExportRegistration], endpoint_id: Optional[str] = None
    ) -> None:
        """
        Lists the exported services
        """
        if endpoint_id:
            matching_eds = [
                x.get_description() for x in configs if x.get_description().get_id() == endpoint_id
            ]
            if matching_eds:
                session.write_line("Endpoint description for endpoint.id={0}:", endpoint_id)
                session.write_line(EDEFWriter().to_string(matching_eds))
        else:
            title = ("Endpoint ID", "Container ID", "Service ID")
            rows = []
            for import_reg in configs:
                ed = import_reg.get_description()
                rows.append((ed.get_id(), ed.get_container_id()[1], ed.get_service_id()))

            session.write_line(self._utils.make_table(title, rows))

    def _list_exported_configs(self, io_handler: ShellSession, endpoint_id: Optional[str] = None) -> None:
        """
        List exported services. If <endpoint_id> given, details on that export
        """
        self._list_exports(
            io_handler, cast(rsa_impl.RemoteServiceAdminImpl, self._rsa)._get_export_regs(), endpoint_id
        )

    def _list_imported_configs(self, io_handler: ShellSession, endpoint_id: Optional[str] = None) -> None:
        """
        List imported endpoints. If <endpoint_id> given, details on that import
        """
        self._list_imports(
            io_handler, cast(rsa_impl.RemoteServiceAdminImpl, self._rsa)._get_import_regs(), endpoint_id
        )

    def _unimport(self, io_handler: ShellSession, endpoint_id: str) -> None:
        """
        Un-import endpoint with given endpoint_id (required)
        """
        import_regs = cast(rsa_impl.RemoteServiceAdminImpl, self._rsa)._get_import_regs()
        found_reg = None
        for import_reg in import_regs:
            ed = import_reg.get_description()
            if ed and ed.get_id() == endpoint_id:
                found_reg = import_reg
        if not found_reg:
            io_handler.write_line(
                "Cannot find import registration with endpoint.id={0}",
                endpoint_id,
            )
        else:
            # now close it
            found_reg.close()

    def _unexport(self, io_handler: ShellSession, endpoint_id: str) -> None:
        """
        Un-export endpoint with given endpoint_id (required)
        """
        # pylint: disable=W0212
        export_regs = cast(rsa_impl.RemoteServiceAdminImpl, self._rsa)._get_export_regs()
        found_reg = None
        for export_reg in export_regs:
            ed = export_reg.get_description()
            if ed and ed.get_id() == endpoint_id:
                found_reg = export_reg
        if not found_reg:
            io_handler.write_line(
                "Cannot find export registration with endpoint.id={0}",
                endpoint_id,
            )
        else:
            # now close it
            found_reg.close()

    def _get_edef_fullname(self) -> str:
        return self._edef_filename

    def _export_service(
        self,
        io_handler: ShellSession,
        service_id: str,
        export_config: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> None:
        """
        Export service with given service.id.
        """
        assert self._context is not None
        svc_ref: Optional[ServiceReference[Any]] = self._context.get_service_reference(
            None, f"(service.id={service_id})"
        )
        if not svc_ref:
            io_handler.write_line(
                "Service with id={0} cannot be found so no service " "can be exported",
                service_id,
            )
            return

        if export_config:
            self._export_config = export_config

        if filename:
            self._edef_filename = filename

        # Finally export with required SERVICE_EXPORTED_INTERFACES = '*'
        # and SERVICE_EXPORTED_CONFIGS to self._export_config
        export_regs = self._rsa.export_service(
            svc_ref,
            {
                SERVICE_EXPORTED_INTERFACES: "*",
                SERVICE_EXPORTED_CONFIGS: self._export_config,
            },
        )
        exported_eds = []
        for export_reg in export_regs:
            exp = export_reg.get_exception()
            if exp:
                io_handler.write_line(
                    "\nException exporting service={0}",
                    export_reg.get_reference(),
                )
                print_exception(exp[0], exp[1], exp[2], limit=None, file=io_handler)
                io_handler.flush()
            else:
                exported_eds.append(export_reg.get_description())

        # write exported_eds to filename
        if self._edef_filename:
            EDEFWriter().write(exported_eds, self._edef_filename)

            io_handler.write_line(
                "Service={0} exported by {1} providers. EDEF written to file={2}",
                svc_ref,
                len(exported_eds),
                self._edef_filename,
            )
        else:
            io_handler.write_line("No output EDEF file given")

    def _import_edef(self, io_handler: ShellSession, edef_file: Optional[str] = None) -> None:
        """
        Import endpoint
        """
        if not edef_file:
            edef_file = self._edef_filename

        full_name = self._get_edef_fullname()
        with open(full_name) as f:
            eds = EDEFReader().parse(f.read())
            io_handler.write_line("Imported {0} endpoints from EDEF file={1}", len(eds), full_name)

        ed: Optional[EndpointDescription]
        for ed in eds:
            if ed is None:
                continue

            import_reg = self._rsa.import_service(ed)
            if import_reg:
                exp = import_reg.get_exception()
                ed = import_reg.get_description()
                if ed is None:
                    io_handler.write_line("Invalid import registration found: {0}", import_reg)
                    continue
                if exp:
                    io_handler.write_line("Exception importing endpoint.id={0}", ed.get_id())
                    print_exception(exp[0], exp[1], exp[2], limit=None, file=io_handler)
                    io_handler.flush()
                else:
                    io_handler.write_line(
                        "Proxy service={0} imported. rsid={1}",
                        import_reg.get_reference(),
                        ed.get_remoteservice_idstr(),
                    )
