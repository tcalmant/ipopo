#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
:author: Thomas Calmant
:copyright: Copyright 2015, isandlaTech
:license: Apache License 2.0
:version: 0.6.3

..

    Copyright 2015 isandlaTech

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

# Module version
__version_info__ = (0, 6, 3)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Pelix
import pelix.constants
from pelix.constants import BundleActivator
from pelix.ipopo.constants import use_ipopo
from pelix.shell import SERVICE_SHELL_COMMAND

# Standard library
import json
import os
import platform
import sys

# ------------------------------------------------------------------------------


class ReportCommands(object):
    """
    Registers report shell commands
    """
    def __init__(self, context):
        """
        Sets up members

        :param context: The bundle context
        """
        self.__context = context

        # Last computed report
        self.__report = None

        # Level -> Methods
        self.__levels = {
            'os': (self.os_details,),
            'os_env': (self.os_env,),
            'python': (self.python_details,),
            'python_path': (self.python_path,),
            'python_modules': (self.python_modules,),
            'pelix_basic': (self.pelix_infos,),
            'pelix_bundles': (self.pelix_bundles,),
            'pelix_services': (self.pelix_services,),
            'pelix': (self.pelix_infos, self.pelix_bundles,
                      self.pelix_services),
            'ipopo': (self.ipopo_instances, self.ipopo_factories),
            'ipopo_instances': (self.ipopo_instances,),
            'ipopo_factories': (self.ipopo_factories,),
            # 'threads': (self.threads_details,),
            # 'memory': (self.memory_details,),
        }

        # Full report: call all methods
        full_reports = set()
        for methods in self.__levels.values():
            full_reports.update(methods)
        self.__levels['full'] = tuple(full_reports)

    @staticmethod
    def get_namespace():
        """
        Retrieves the name space of this command handler
        """
        return "report"

    def get_methods(self):
        """
        Retrieves the list of tuples (command, method) for this command handler
        """
        return [('levels', self.print_levels),
                ('make', self.make_report),
                ('clear', self.clear_report),
                ('show', self.show_report),
                ('write', self.write_report),]

    def print_levels(self, session):
        """
        Lists available levels
        """
        levels = sorted(self.__levels)
        lines = []
        for level in levels:
            methods = sorted(method.__name__ for method in self.__levels[level])
            lines.append('- ' + level + ': ')
            lines.append('\t' + ', '.join(methods))
        session.write_line('\n'.join(lines))

    @staticmethod
    def os_details():
        """
        Returns a dictionary containing details about the operating system
        """
        # Compute architecture and linkage
        bits, linkage = platform.architecture()
        results = {
            # Machine details
            'platform.arch.bits': bits,
            'platform.arch.linkage': linkage,
            'platform.machine': platform.machine(),
            'platform.process': platform.processor(),
            'sys.byteorder': sys.byteorder,

            # OS details
            'os.name': os.name,
            'sys.platform': sys.platform,
            'platform.system': platform.system(),
            'platform.release': platform.release(),
            'platform.version': platform.version(),
            'encoding.filesystem': sys.getfilesystemencoding(),
        }

        try:
            # Available since Python 3.4
            results['os.cpu_count'] = os.cpu_count()
        except AttributeError:
            results['os.cpu_count'] = None

        try:
            # Only for Unix
            results['sys.dlopenflags'] = sys.getdlopenflags()
        except AttributeError:
            results['sys.dlopenflags'] = None

        return results

    @staticmethod
    def os_env():
        """
        Returns a copy of the environment variables
        """
        return os.environ.copy()

    @staticmethod
    def python_details():
        """
        Returns a dictionary containing details about the Python interpreter
        """
        build_no, build_date = platform.python_build()
        results = {
            # Version of interpreter
            'build.number': build_no,
            'build.date': build_date,
            'compiler': platform.python_compiler(),
            'branch': platform.python_branch(),
            'revision': platform.python_revision(),
            'implementation': platform.python_implementation(),
            'version': '.'.join(str(v) for v in sys.version_info),

            # API version
            'api.version': sys.api_version,

            # Installation details
            'prefix': sys.prefix,
            'base_prefix': getattr(sys, 'base_prefix', None),
            'exec_prefix': sys.exec_prefix,
            'base_exec_prefix': getattr(sys, 'base_exec_prefix', None),

            # Execution details
            'executable': sys.executable,
            'argv': sys.argv,
            'encoding.default': sys.getdefaultencoding(),

            # Other details, ...
            'recursion_limit': sys.getrecursionlimit()
        }

        # Threads implementation details
        thread_info = getattr(sys, 'thread_info', (None, None, None))
        results['thread_info.name'] = thread_info[0]
        results['thread_info.lock'] = thread_info[1]
        results['thread_info.version'] = thread_info[2]

        # ABI flags (POSIX only)
        results['abiflags'] = getattr(sys, 'abiflags', None)

        # -X options (CPython only)
        results['x_options'] = getattr(sys, '_xoptions', None)

        return results

    @staticmethod
    def python_path():
        """
        Returns the content of sys.path
        """
        return {
            'sys.path': sys.path[:],
            'sys.path_hooks': getattr(sys, 'path_hooks', None),
            'sys.meta_path': sys.meta_path
        }

    @staticmethod
    def python_modules():
        """
        Returns the list of Python modules and their file
        """
        imported = {}
        results = {'builtins': sys.builtin_module_names,
                   'imported': imported}
        for module_name, module in sys.modules.items():
            if module_name not in sys.builtin_module_names:
                try:
                    imported[module_name] = module.__file__
                except AttributeError:
                    imported[module_name] = "<no __file__ attribute :: {0}>" \
                        .format(repr(module))

        return results

    def pelix_infos(self):
        """
        Basic information about the Pelix framework instance
        """
        framework = self.__context.get_bundle(0)
        return {
            "version": framework.get_version(),
            "properties": framework.get_properties(),
        }

    def pelix_bundles(self):
        """
        List of installed bundles
        """
        framework = self.__context.get_bundle(0)
        return {bundle.get_bundle_id(): {
            "name": bundle.get_symbolic_name(),
            "version": bundle.get_version(),
            "state": bundle.get_state(),
            "location": bundle.get_location(),
        } for bundle in framework.get_bundles()}

    def pelix_services(self):
        """
        List of registered services
        """
        return {svc_ref.get_property(pelix.constants.SERVICE_ID): {
            "specifications": svc_ref.get_property(pelix.constants.OBJECTCLASS),
            "ranking": svc_ref.get_property(pelix.constants.SERVICE_RANKING),
            "properties": svc_ref.get_properties(),
            "bundle.id": svc_ref.get_bundle().get_bundle_id(),
            "bundle.name": svc_ref.get_bundle().get_symbolic_name(),
        } for svc_ref in self.__context.get_all_service_references(None)}

    def ipopo_factories(self):
        """
        List of iPOPO factories
        """
        with use_ipopo(self.__context) as ipopo:
            return {name: ipopo.get_factory_details(name)
                    for name in ipopo.get_factories()}

    def ipopo_instances(self):
        """
        List of iPOPO instances
        """
        with use_ipopo(self.__context) as ipopo:
            return {instance[0]: ipopo.get_instance_details(instance[0])
                    for instance in ipopo.get_instances()}

    def make_report(self, session, *levels):
        """
        Prepares the report

        :param levels: list of levels
        """
        if not levels:
            levels = ['full']

        try:
            methods = {method
                       for level in levels
                       for method in self.__levels[level]}
        except KeyError as ex:
            session.write_line("Unknown report level: {0}", ex)
            self.__report = None
        else:
            self.__report = {method.__name__: method() for method in methods}
            self.__report['levels'] = levels
        return self.__report

    def clear_report(self, session):
        """
        Deletes the report in memory
        """
        self.__report = None

    @staticmethod
    def json_converter(obj):
        """
        Returns the representation string (repr()) for objects that can't be
        converted to JSON
        """
        return str(obj)

    def __dump_json(self, data):
        """
        Converts the given object to a pretty-formatted JSON string

        :param data: the object to convert to JSON
        :return: A pretty-formatted JSON string
        """
        # Don't forget the empty line at the end of the file
        return json.dumps(data, sort_keys=True, indent=4,
                          separators=(',', ': '),
                          default=self.json_converter) + '\n'

    def show_report(self, session, *levels):
        """
        Shows the report that has been generated
        """
        if not self.__report:
            self.make_report(session, *levels)

        if self.__report:
            session.write_line(self.__dump_json(self.__report))
        else:
            session.write_line("No report to show")

    def write_report(self, session, filename):
        """
        Writes the report in JSON format to the given file
        """
        if not self.__report:
            session.write_line("No report to write down")
            return

        try:
            with open(filename, "w+") as fp:
                fp.write(self.__dump_json(self.__report))
        except IOError as ex:
            session.write_line("Error writing to file: {0}", ex)

# ------------------------------------------------------------------------------


@BundleActivator
class Activator(object):
    """
    Activator class for Pelix
    """
    def __init__(self):
        """
        Sets up the activator
        """
        self._svc_reg = None

    def start(self, context):
        """
        Bundle starting
        """
        # Prepare the shell utility service
        self._svc_reg = context.register_service(
            SERVICE_SHELL_COMMAND, ReportCommands(context), {})

    def stop(self, context):
        """
        Bundle stopping
        """
        # Unregister the services
        if self._svc_reg is not None:
            self._svc_reg.unregister()
            self._svc_reg = None
