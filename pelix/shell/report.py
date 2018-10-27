#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Report generation service and shell command.

This bundle provides a service and a shell command to generates reports, i.e.
dictionaries containing the description of the current Pelix framework and of
its environement.

:author: Thomas Calmant
:copyright: Copyright 2018, Thomas Calmant
:license: Apache License 2.0
:version: 0.8.1

..

    Copyright 2018 Thomas Calmant

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

# Standard library
import datetime
import inspect
import json
import linecache
import os
import platform
import socket
import sys
import threading
import time

# Pelix
import pelix.constants
from pelix.constants import BundleActivator, BundleException
from pelix.ipopo.constants import use_ipopo
from pelix.shell import SERVICE_SHELL_COMMAND, SERVICE_SHELL_REPORT

# ------------------------------------------------------------------------------

# Public API
__all__ = ("format_frame_info",)

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


def format_frame_info(frame):
    """
    Formats the given stack frame to show its position in the code and
    part of its context

    :param frame: A stack frame
    """
    # Same as in traceback.extract_stack
    line_no = frame.f_lineno
    code = frame.f_code
    filename = code.co_filename
    method_name = code.co_name
    linecache.checkcache(filename)

    try:
        # Try to get the type of the calling object
        instance = frame.f_locals["self"]
        method_name = "{0}::{1}".format(type(instance).__name__, method_name)
    except KeyError:
        # Not called from a bound method
        pass

    # File & line
    output_lines = [
        '  File "{0}", line {1}, in {2}'.format(filename, line_no, method_name)
    ]

    # Arguments
    if frame.f_locals:
        # Pypy keeps f_locals as an empty dictionary
        arg_info = inspect.getargvalues(frame)
        for name in arg_info.args:
            try:
                output_lines.append(
                    "    - {0:s} = {1}".format(name, repr(frame.f_locals[name]))
                )
            except TypeError:
                # Happens in dict/list-comprehensions in Python 2.x
                name = name[0]
                output_lines.append(
                    "    - {0:s} = {1}".format(name, repr(frame.f_locals[name]))
                )

        if arg_info.varargs:
            output_lines.append(
                "    - *{0:s} = {1}".format(
                    arg_info.varargs, frame.f_locals[arg_info.varargs]
                )
            )

        if arg_info.keywords:
            output_lines.append(
                "    - **{0:s} = {1}".format(
                    arg_info.keywords, frame.f_locals[arg_info.keywords]
                )
            )

    # Line block
    lines = _extract_lines(filename, frame.f_globals, line_no, 3)
    if lines:
        output_lines.append("")
        prefix = "      "
        output_lines.append(
            "{0}{1}".format(prefix, "\n{0}".format(prefix).join(lines))
        )
    return "\n".join(output_lines)


def _extract_lines(filename, f_globals, line_no, around):
    """
    Extracts a block of lines from the given file

    :param filename: Name of the source file
    :param f_globals: Globals of the frame of the current code
    :param line_no: Current line of code
    :param around: Number of line to print before and after the current one
    """
    current_line = linecache.getline(filename, line_no, f_globals)
    if not current_line:
        # No data on this line
        return ""

    lines = []
    # Add some lines before
    for pre_line_no in range(line_no - around, line_no):
        pre_line = linecache.getline(filename, pre_line_no, f_globals)
        lines.append("{0}".format(pre_line.rstrip()))

    # The line itself
    lines.append("{0}".format(current_line.rstrip()))

    # Add some lines after
    for pre_line_no in range(line_no + 1, line_no + around + 1):
        pre_line = linecache.getline(filename, pre_line_no, f_globals)
        lines.append("{0}".format(pre_line.rstrip()))

    # Smart left strip
    minimal_tab = None
    for line in lines:
        if line.strip():
            tab = len(line) - len(line.lstrip())
            if minimal_tab is None or tab < minimal_tab:
                minimal_tab = tab

    if minimal_tab > 0:
        lines = [line[minimal_tab:] for line in lines]

    # Add some place for a marker
    marked_line = ">> {0}".format(lines[around])
    lines = ["   {0}".format(line) for line in lines]
    lines[around] = marked_line
    lines.append("")
    return lines


# ------------------------------------------------------------------------------


class _ReportCommands(object):
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
            # OS and machine details
            "os": (self.os_details,),
            "os_env": (self.os_env,),
            # Python
            "python": (self.python_details,),
            "python_path": (self.python_path,),
            "python_modules": (self.python_modules,),
            "process": (self.process_details,),
            # Pelix
            "pelix_basic": (self.pelix_infos,),
            "pelix_bundles": (self.pelix_bundles,),
            "pelix_services": (self.pelix_services,),
            # iPOPO
            "ipopo_instances": (self.ipopo_instances,),
            "ipopo_factories": (self.ipopo_factories,),
            # Extra reports
            "threads": (self.threads_list,),
            "network": (self.network_details,),
        }

        # Aliases, to ease the generation of multiple reports at once
        # Alias -> Levels
        self.__aliases = {
            # Full report
            "full": tuple(self.__levels.keys()),
            # Pelix & iPOPO
            "pelix": ("pelix_basic", "pelix_bundles", "pelix_services"),
            "ipopo": ("ipopo_instances", "ipopo_factories"),
            # Application description
            "app": ("os", "process", "python", "python_path", "os_env"),
            # Standard description levels
            "minimal": ("os", "python", "pelix_basic"),
            "standard": (
                "minimal",
                "python_path",
                "python_modules",
                "process",
                "pelix_bundles",
                "ipopo_factories",
            ),
            "debug": ("standard", "pelix_services", "ipopo_instances"),
        }

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
        return [
            ("levels", self.print_levels),
            ("make", self.make_report),
            ("clear", self.clear_report),
            ("show", self.show_report),
            ("write", self.write_report),
        ]

    def get_level_methods(self, level):
        """
        Returns the methods to call for the given level of report

        :param level: The level of report
        :return: The set of methods to call to fill the report
        :raise KeyError: Unknown level or alias
        """
        try:
            # Real name of the level
            return set(self.__levels[level])
        except KeyError:
            # Alias
            result = set()
            for sub_level in self.__aliases[level]:
                result.update(self.get_level_methods(sub_level))
            return result

    def get_levels(self):
        """
        Returns a copy of the dictionary of levels.

        The key is the name of the report level, the value is the tuple of
        methods to call for that level.
        Multiple levels can call the same method.

        :return: A dictionary of lists of methods to call
        """
        return set(self.__levels).union(self.__aliases)

    def print_levels(self, session):
        """
        Lists available levels
        """
        lines = []
        for level in sorted(self.get_levels()):
            methods = sorted(
                method.__name__ for method in self.get_level_methods(level)
            )
            lines.append("- {0}:".format(level))
            lines.append("\t{0}".format(", ".join(methods)))
        session.write_line("\n".join(lines))

    @staticmethod
    def os_details():
        """
        Returns a dictionary containing details about the operating system
        """
        # Compute architecture and linkage
        bits, linkage = platform.architecture()
        results = {
            # Machine details
            "platform.arch.bits": bits,
            "platform.arch.linkage": linkage,
            "platform.machine": platform.machine(),
            "platform.process": platform.processor(),
            "sys.byteorder": sys.byteorder,
            # OS details
            "os.name": os.name,
            "host.name": socket.gethostname(),
            "sys.platform": sys.platform,
            "platform.system": platform.system(),
            "platform.release": platform.release(),
            "platform.version": platform.version(),
            "encoding.filesystem": sys.getfilesystemencoding(),
        }

        # Paths and line separators
        for name in "sep", "altsep", "pathsep", "linesep":
            results["os.{0}".format(name)] = getattr(os, name, None)

        try:
            # Available since Python 3.4
            results["os.cpu_count"] = os.cpu_count()
        except AttributeError:
            results["os.cpu_count"] = None

        try:
            # Only for Unix
            # pylint: disable=E1101
            results["sys.dlopenflags"] = sys.getdlopenflags()
        except AttributeError:
            results["sys.dlopenflags"] = None

        return results

    @staticmethod
    def os_env():
        """
        Returns a copy of the environment variables
        """
        return os.environ.copy()

    @staticmethod
    def process_details():
        """
        Returns details about the current process
        """
        results = {"argv": sys.argv, "working.directory": os.getcwd()}

        # Process ID and execution IDs (UID, GID, Login, ...)
        for key, method in {
            "pid": "getpid",
            "ppid": "getppid",
            "login": "getlogin",
            "uid": "getuid",
            "euid": "geteuid",
            "gid": "getgid",
            "egid": "getegid",
            "groups": "getgroups",
        }.items():
            try:
                results[key] = getattr(os, method)()
            except (AttributeError, OSError):
                results[key] = None
        return results

    @staticmethod
    def network_details():
        """
        Returns details about the network links
        """
        # Get IPv4 details
        ipv4_addresses = [
            info[4][0]
            for info in socket.getaddrinfo(
                socket.gethostname(), None, socket.AF_INET
            )
        ]

        # Add localhost
        ipv4_addresses.extend(
            info[4][0]
            for info in socket.getaddrinfo("localhost", None, socket.AF_INET)
        )

        # Filter addresses
        ipv4_addresses = sorted(set(ipv4_addresses))

        try:
            # Get IPv6 details
            ipv6_addresses = [
                info[4][0]
                for info in socket.getaddrinfo(
                    socket.gethostname(), None, socket.AF_INET6
                )
            ]

            # Add localhost
            ipv6_addresses.extend(
                info[4][0]
                for info in socket.getaddrinfo(
                    "localhost", None, socket.AF_INET6
                )
            )

            # Filter addresses
            ipv6_addresses = sorted(set(ipv6_addresses))
        except (socket.gaierror, AttributeError):
            # AttributeError: AF_INET6 is missing in some versions of Python
            ipv6_addresses = None

        return {
            "IPv4": ipv4_addresses,
            "IPv6": ipv6_addresses,
            "host.name": socket.gethostname(),
            "host.fqdn": socket.getfqdn(),
        }

    @staticmethod
    def python_details():
        """
        Returns a dictionary containing details about the Python interpreter
        """
        build_no, build_date = platform.python_build()
        results = {
            # Version of interpreter
            "build.number": build_no,
            "build.date": build_date,
            "compiler": platform.python_compiler(),
            "branch": platform.python_branch(),
            "revision": platform.python_revision(),
            "implementation": platform.python_implementation(),
            "version": ".".join(str(v) for v in sys.version_info),
            # API version
            "api.version": sys.api_version,
            # Installation details
            "prefix": sys.prefix,
            "base_prefix": getattr(sys, "base_prefix", None),
            "exec_prefix": sys.exec_prefix,
            "base_exec_prefix": getattr(sys, "base_exec_prefix", None),
            # Execution details
            "executable": sys.executable,
            "encoding.default": sys.getdefaultencoding(),
            # Other details, ...
            "recursion_limit": sys.getrecursionlimit(),
        }

        # Threads implementation details
        thread_info = getattr(sys, "thread_info", (None, None, None))
        results["thread_info.name"] = thread_info[0]
        results["thread_info.lock"] = thread_info[1]
        results["thread_info.version"] = thread_info[2]

        # ABI flags (POSIX only)
        results["abiflags"] = getattr(sys, "abiflags", None)

        # -X options (CPython only)
        results["x_options"] = getattr(sys, "_xoptions", None)
        return results

    @staticmethod
    def python_path():
        """
        Returns the content of sys.path
        """
        return {
            "sys.path": sys.path[:],
            "sys.path_hooks": getattr(sys, "path_hooks", None),
            "sys.meta_path": sys.meta_path,
        }

    @staticmethod
    def python_modules():
        """
        Returns the list of Python modules and their file
        """
        imported = {}
        results = {"builtins": sys.builtin_module_names, "imported": imported}
        for module_name, module_ in sys.modules.items():
            if module_name not in sys.builtin_module_names:
                try:
                    imported[module_name] = inspect.getfile(module_)
                except TypeError:
                    imported[
                        module_name
                    ] = "<no file information :: {0}>".format(repr(module_))

        return results

    def pelix_infos(self):
        """
        Basic information about the Pelix framework instance
        """
        framework = self.__context.get_framework()
        return {
            "version": framework.get_version(),
            "properties": framework.get_properties(),
        }

    def pelix_bundles(self):
        """
        List of installed bundles
        """
        framework = self.__context.get_framework()
        return {
            bundle.get_bundle_id(): {
                "name": bundle.get_symbolic_name(),
                "version": bundle.get_version(),
                "state": bundle.get_state(),
                "location": bundle.get_location(),
            }
            for bundle in framework.get_bundles()
        }

    def pelix_services(self):
        """
        List of registered services
        """
        return {
            svc_ref.get_property(pelix.constants.SERVICE_ID): {
                "specifications": svc_ref.get_property(
                    pelix.constants.OBJECTCLASS
                ),
                "ranking": svc_ref.get_property(
                    pelix.constants.SERVICE_RANKING
                ),
                "properties": svc_ref.get_properties(),
                "bundle.id": svc_ref.get_bundle().get_bundle_id(),
                "bundle.name": svc_ref.get_bundle().get_symbolic_name(),
            }
            for svc_ref in self.__context.get_all_service_references(None)
        }

    def ipopo_factories(self):
        """
        List of iPOPO factories
        """
        try:
            with use_ipopo(self.__context) as ipopo:
                return {
                    name: ipopo.get_factory_details(name)
                    for name in ipopo.get_factories()
                }
        except BundleException:
            # iPOPO is not available:
            return None

    def ipopo_instances(self):
        """
        List of iPOPO instances
        """
        try:
            with use_ipopo(self.__context) as ipopo:
                return {
                    instance[0]: ipopo.get_instance_details(instance[0])
                    for instance in ipopo.get_instances()
                }
        except BundleException:
            # iPOPO is not available:
            return None

    @staticmethod
    def threads_list():
        """
        Lists the active threads and their current code line
        """
        results = {}

        # pylint: disable=W0212
        try:
            # Extract frames
            frames = sys._current_frames()

            # Get the thread ID -> Thread mapping
            names = threading._active.copy()
        except AttributeError:
            # Extraction not available
            return results

        # Sort by thread ID
        thread_ids = sorted(frames.keys())
        for thread_id in thread_ids:
            # Get the corresponding stack
            stack = frames[thread_id]

            # Try to get the thread name
            try:
                name = names[thread_id].name
            except KeyError:
                name = "<unknown>"

            trace_lines = []
            frame = stack
            while frame is not None:
                # Store the line information
                trace_lines.append(format_frame_info(frame))

                # Previous frame...
                frame = frame.f_back

            # Construct the thread description
            results[thread_id] = {
                "name": name,
                "stacktrace": "\n".join(reversed(trace_lines)),
            }

        return results

    def make_report(self, session, *levels):
        """
        Prepares the report at the requested level(s)
        """
        if not levels:
            levels = ["full"]

        try:
            # List the methods to call, avoiding double-calls
            methods = set()
            for level in levels:
                methods.update(self.get_level_methods(level))
        except KeyError as ex:
            # Unknown level
            session.write_line("Unknown report level: {0}", ex)
            self.__report = None
        else:
            # Call each method
            self.__report = {method.__name__: method() for method in methods}
            # Describe the report
            self.__report["report"] = {
                "report.levels": levels,
                "time.stamp": time.time(),
                "time.local": str(datetime.datetime.now()),
                "time.utc": str(datetime.datetime.utcnow()),
            }

        return self.__report

    def clear_report(self, _):
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

    def to_json(self, data):
        """
        Converts the given object to a pretty-formatted JSON string

        :param data: the object to convert to JSON
        :return: A pretty-formatted JSON string
        """
        # Don't forget the empty line at the end of the file
        return (
            json.dumps(
                data,
                sort_keys=True,
                indent=4,
                separators=(",", ": "),
                default=self.json_converter,
            )
            + "\n"
        )

    def show_report(self, session, *levels):
        """
        Shows the report that has been generated
        """
        if levels:
            self.make_report(session, *levels)

        if self.__report:
            session.write_line(self.to_json(self.__report))
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
            with open(filename, "w+") as out_file:
                out_file.write(self.to_json(self.__report))
        except IOError as ex:
            session.write_line("Error writing to file: {0}", ex)


# ------------------------------------------------------------------------------


@BundleActivator
class _Activator(object):
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
            [SERVICE_SHELL_COMMAND, SERVICE_SHELL_REPORT],
            _ReportCommands(context),
            {},
        )

    def stop(self, _):
        """
        Bundle stopping
        """
        # Unregister the services
        if self._svc_reg is not None:
            self._svc_reg.unregister()
            self._svc_reg = None
