#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Remote Service Admin Shell Commands

:author: Scott Lewis
:copyright: Copyright 2018, Scott Lewis
:license: Apache License 2.0
:version: 0.8.1

..

    Copyright 2018 Scott Lewis

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

from threading import RLock
from traceback import print_exception
import os

try:
    # pylint: disable=W0611
    from typing import Any, Tuple, List, Callable, Optional
    from pelix.framework import BundleContext
    from pelix.rsa.remoteserviceadmin import (
        ImportRegistration,
        ExportRegistration,
    )
    from pelix.rsa.providers.distribution import Container, DistributionProvider
    from pelix.shell.beans import ShellSession
except ImportError:
    pass

from pelix.constants import SERVICE_ID
from pelix.ipopo.decorators import (
    ComponentFactory,
    Provides,
    Instantiate,
    Validate,
    Requires,
    Property,
    BindField,
    UnbindField,
    Invalidate,
)
from pelix.shell import SERVICE_SHELL_COMMAND, SERVICE_SHELL_UTILS

from pelix.rsa import (
    SERVICE_REMOTE_SERVICE_ADMIN,
    SERVICE_EXPORTED_CONFIGS,
    SERVICE_EXPORTED_INTERFACES,
    prop_dot_suffix,
)
from pelix.rsa.edef import EDEFReader, EDEFWriter
from pelix.rsa.remoteserviceadmin import RemoteServiceAdminEvent

from pelix.rsa.providers.distribution import (
    SERVICE_IMPORT_CONTAINER,
    SERVICE_EXPORT_CONTAINER,
    SERVICE_IMPORT_DISTRIBUTION_PROVIDER,
    SERVICE_EXPORT_DISTRIBUTION_PROVIDER,
)

# ------------------------------------------------------------------------------
# Module version

__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


def _full_class_name(obj):
    """
    Returns the full name of the class of the given object

    :param obj: Any Python object
    :return: The full name of the class of the object (if possible)
    """
    module = obj.__class__.__module__
    if module is None or module == str.__class__.__module__:
        return obj.__class__.__name__
    return module + "." + obj.__class__.__name__


RSA_COMMAND_NAME_PROP = "rsa.command"
RSA_COMMAND_FILENAME_PROP = "edeffilename"
RSA_COMMAND_EXPORT_CONFIG_PROP = "defaultexportconfig"

# ------------------------------------------------------------------------------


@ComponentFactory("rsa-command-factory")
@Requires("_utils", SERVICE_SHELL_UTILS)
@Requires("_rsa", SERVICE_REMOTE_SERVICE_ADMIN)
@Requires("_imp_containers", SERVICE_IMPORT_CONTAINER, True, True)
@Requires("_exp_containers", SERVICE_EXPORT_CONTAINER, True, True)
@Requires(
    "_imp_dist_providers", SERVICE_IMPORT_DISTRIBUTION_PROVIDER, True, True
)
@Requires(
    "_exp_dist_providers", SERVICE_EXPORT_DISTRIBUTION_PROVIDER, True, True
)
@Provides([SERVICE_SHELL_COMMAND])
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
class RSACommandHandler(object):
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

    def __init__(self):
        self._context = None  # type: BundleContext
        self._utils = None
        self._rsa = None
        self._imp_containers = []
        self._exp_containers = []
        self._imp_dist_providers = []
        self._exp_dist_providers = []
        self._edef_filename = None
        self._export_config = None
        self._bind_lock = RLock()

    def _bind_lists(self, field, service):
        # type: (List[Any], Any) -> None
        """
        Thread-safe handling of addition in a list of bound services

        :param field: Name of the injected field
        :param service: Injected service
        """
        with self._bind_lock:
            field.append(service)

    def _unbind_lists(self, field, service):
        # type: (List[Any], Any) -> None
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
    def _bind_imp_containers(self, field, service, service_ref):
        # pylint: disable=W0613
        self._bind_lists(self._imp_containers, service)

    @UnbindField("_imp_containers")
    def _unbind_imp_containers(self, field, service, service_ref):
        # pylint: disable=W0613
        self._unbind_lists(self._imp_containers, service)

    @BindField("_exp_containers")
    def _bind_exp_containers(self, field, service, service_ref):
        # pylint: disable=W0613
        self._bind_lists(self._exp_containers, service)

    @UnbindField("_exp_containers")
    def _unbind_exp_containers(self, field, service, service_ref):
        # pylint: disable=W0613
        self._unbind_lists(self._exp_containers, service)

    @BindField("_imp_dist_providers")
    def _bind_imp_dist_providers(self, field, service, service_ref):
        # pylint: disable=W0613
        self._bind_lists(self._imp_dist_providers, service)

    @UnbindField("_imp_dist_providers")
    def _unbind_imp_dist_providers(self, field, service, service_ref):
        # pylint: disable=W0613
        self._unbind_lists(self._imp_dist_providers, service)

    @BindField("_exp_dist_providers")
    def _bind_exp_dist_providers(self, field, service, service_ref):
        # pylint: disable=W0613
        self._bind_lists(self._exp_dist_providers, service)

    @UnbindField("_exp_dist_providers")
    def _unbind_exp_dist_providers(self, field, service, service_ref):
        # pylint: disable=W0613
        self._unbind_lists(self._exp_dist_providers, service)

    def _get_containers(self, container_id=None):
        # type: (Optional[str]) -> List[Container]
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

    def _get_dist_providers(self, provider_id=None):
        # type: (Optional[str]) -> List[DistributionProvider]
        """
        Gets the list of import and export providers

        :param provider_id: An optional provider ID
        :return: All providers or those matching the given ID
        """
        with self._bind_lock:
            providers = set(self._imp_dist_providers + self._exp_dist_providers)
            if provider_id:
                return [
                    p for p in providers if p.get_config_name() == provider_id
                ]

            return list(providers)

    @Validate
    def _validate(self, bundle_context):
        # type: (BundleContext) -> None
        """
        Component validated
        """
        self._context = bundle_context

    @Invalidate
    def _invalidate(self, _):
        # type: (BundleContext) -> None
        """
        Component invalidated
        """
        if self._edef_filename and os.path.isfile(self._edef_filename):
            os.remove(self._edef_filename)

    @staticmethod
    def get_namespace():
        """
        Returns the namespace of the shell commands
        """
        return RSACommandHandler.SHELL_NAMESPACE

    def get_methods(self):
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

    def remote_admin_event(self, event):
        # type: (RemoteServiceAdminEvent) -> None
        """
        Handle a remote service admin event
        """
        if event.get_type() == RemoteServiceAdminEvent.EXPORT_REGISTRATION:
            EDEFWriter().write([event.get_description()], self._edef_filename)

    def _show_defaults(self, io_handler):
        # type: (ShellSession) -> None
        """
        Show default edeffile and default export_config
        """
        io_handler.write_line(
            "Defaults\n\texport_config={0}\n\tEDEF file={1};exists={2}",
            self._export_config,
            self._edef_filename,
            os.path.isfile(self._edef_filename),
        )

    def _set_defaults(self, io_handler, export_config, edef_file=None):
        # type: (ShellSession, str, str) -> None
        """
        Set the export_config and optionally the edef_file default values
        """
        self._export_config = export_config
        if edef_file:
            self._edef_filename = edef_file
        self._show_defaults(io_handler)

    def _show_edef(self, io_handler):
        # type: (ShellSession) -> None
        """
        Show contents of EDEF file
        """
        if not os.path.isfile(self._edef_filename):
            io_handler.write_line(
                "EDEF file '{0}' does not exist!", self._edef_filename
            )
        else:
            with open(self._edef_filename, "r") as f:
                eds = EDEFReader().parse(f.read())

            io_handler.write_line(EDEFWriter().to_string(eds))

    def _list_providers(self, io_handler, provider_id=None):
        # type: (ShellSession, str) -> None
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
                rows = [
                    (p.get_config_name(), _full_class_name(p))
                    for p in providers
                ]
                io_handler.write_line(self._utils.make_table(title, rows))

    def _list_containers(self, io_handler, container_id=None):
        # type: (ShellSession, str) -> None
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

    def _list_imports(self, session, import_regs, endpoint_id=None):
        # type: (ShellSession, List[ImportRegistration], str) -> None
        """
        Lists the imported services
        """
        if endpoint_id:
            matching_eds = [
                x.get_description()
                for x in import_regs
                if x.get_description().get_id() == endpoint_id
            ]
            if matching_eds:
                session.write_line(
                    "Endpoint description for endpoint.id={0}:", endpoint_id
                )
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
                rows.append(
                    (
                        ed.get_id(),
                        ed.get_container_id()[1],
                        import_reg.get_reference().get_property(SERVICE_ID),
                        ed.get_service_id(),
                    )
                )

            session.write_line(self._utils.make_table(title, rows))

    def _list_exports(self, session, configs, endpoint_id=None):
        # type: (ShellSession, List[ExportRegistration], str) -> None
        """
        Lists the exported services
        """
        if endpoint_id:
            matching_eds = [
                x.get_description()
                for x in configs
                if x.get_description().get_id() == endpoint_id
            ]
            if matching_eds:
                session.write_line(
                    "Endpoint description for endpoint.id={0}:", endpoint_id
                )
                session.write_line(EDEFWriter().to_string(matching_eds))
        else:
            title = ("Endpoint ID", "Container ID", "Service ID")
            rows = []
            for import_reg in configs:
                ed = import_reg.get_description()
                rows.append(
                    (ed.get_id(), ed.get_container_id()[1], ed.get_service_id())
                )

            session.write_line(self._utils.make_table(title, rows))

    def _list_exported_configs(self, io_handler, endpoint_id=None):
        # type: (ShellSession, str) -> None
        # pylint: disable=W0212
        """
        List exported services. If <endpoint_id> given, details on that export
        """
        self._list_exports(
            io_handler, self._rsa._get_export_regs(), endpoint_id
        )

    def _list_imported_configs(self, io_handler, endpoint_id=None):
        # type: (ShellSession, str) -> None
        # pylint: disable=W0212
        """
        List imported endpoints. If <endpoint_id> given, details on that import
        """
        self._list_imports(
            io_handler, self._rsa._get_import_regs(), endpoint_id
        )

    def _unimport(self, io_handler, endpoint_id):
        # type: (ShellSession, str) -> None
        # pylint: disable=W0212
        """
        Un-import endpoint with given endpoint_id (required)
        """
        import_regs = self._rsa._get_import_regs()
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

    def _unexport(self, io_handler, endpoint_id):
        # type: (ShellSession, str) -> None
        """
        Un-export endpoint with given endpoint_id (required)
        """
        # pylint: disable=W0212
        export_regs = self._rsa._get_export_regs()
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

    def _get_edef_fullname(self):
        # type: () -> str
        return self._edef_filename

    def _export_service(
        self, io_handler, service_id, export_config=None, filename=None
    ):
        # type: (ShellSession, str, str, str) -> None
        """
        Export service with given service.id.
        """
        svc_ref = self._context.get_service_reference(
            None, "(service.id={0})".format(service_id)
        )
        if not svc_ref:
            io_handler.write_line(
                "Service with id={0} cannot be found so no service "
                "can be exported",
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
                print_exception(
                    exp[0], exp[1], exp[2], limit=None, file=io_handler
                )
                io_handler.flush()
            else:
                exported_eds.append(export_reg.get_description())

        # write exported_eds to filename
        EDEFWriter().write(exported_eds, self._edef_filename)

        io_handler.write_line(
            "Service={0} exported by {1} providers. EDEF written to file={2}",
            svc_ref,
            len(exported_eds),
            self._edef_filename,
        )

    def _import_edef(self, io_handler, edef_file=None):
        # type: (ShellSession, str) -> None
        """
        Import endpoint
        """
        if not edef_file:
            edef_file = self._edef_filename

        full_name = self._get_edef_fullname()
        with open(full_name) as f:
            eds = EDEFReader().parse(f.read())
            io_handler.write_line(
                "Imported {0} endpoints from EDEF file={1}", len(eds), full_name
            )

        for ed in eds:
            import_reg = self._rsa.import_service(ed)
            if import_reg:
                exp = import_reg.get_exception()
                ed = import_reg.get_description()
                if exp:
                    io_handler.write_line(
                        "Exception importing endpoint.id={0}", ed.get_id()
                    )
                    print_exception(
                        exp[0], exp[1], exp[2], limit=None, file=io_handler
                    )
                    io_handler.flush()
                else:
                    io_handler.write_line(
                        "Proxy service={0} imported. rsid={1}",
                        import_reg.get_reference(),
                        ed.get_remoteservice_idstr(),
                    )
