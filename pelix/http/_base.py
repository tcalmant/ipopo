#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Transport-independent part of the Pelix HTTP service implementations.

This module is private: it is shared by :mod:`pelix.http.basic` and
:mod:`pelix.http.basic_async` and is not part of the public API.

It holds everything that does not depend on the underlying HTTP server: the
servlet registry, the path matching, the error pages, the logging helpers and
the iPOPO binding logic.

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 3.2.2

..

    Copyright 2026 Thomas Calmant

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

import html
import logging
import re
import socket
import threading
import uuid
from dataclasses import dataclass
from typing import Any, cast

import pelix.http as http
import pelix.ipopo.constants as constants
import pelix.remote
import pelix.utilities as utilities
from pelix.internals.registry import ServiceReference
from pelix.ipopo.decorators import HiddenProperty, Property

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

HTTP_SERVICE_EXTRA = "http.extra"
""" HTTP service extra properties (dictionary) """

DEFAULT_BIND_ADDRESS = "0.0.0.0"
""" By default, bind to all IPv4 interfaces """

LOCALHOST_ADDRESS = "127.0.0.1"
"""
Local address, if None is given as binding address, instead of the default one
"""

DEFAULT_REQUEST_QUEUE_SIZE = 5
""" Default size of the queue of clients waiting to be handled """

_MULTIPLE_SLASHES = re.compile("/+")
""" Matches a sequence of consecutive slashes """

AnyServlet = http.Servlet | http.AsyncServlet | http.WebSocketHandler
""" Any kind of servlet service (sync, async, web socket, ...) """

ServletEntry = tuple[AnyServlet, dict[str, Any], http.ServletType]
""" Servlet registry entry: (servlet, parameters, type) """

# ------------------------------------------------------------------------------


def normalize_request_path(raw_path: str) -> str:
    """
    Normalizes the path of an incoming request: removes the query string and
    collapses the sequences of consecutive slashes.

    :param raw_path: The raw request path
    :return: The path to use to look for a servlet
    """
    return _MULTIPLE_SLASHES.sub("/", raw_path.split("?", 1)[0])


def compute_sub_path(full_path: str, prefix: str) -> str:
    """
    Computes the servlet-relative path of a request, i.e. the part of the path
    which follows the prefix the servlet has been registered on.

    :param full_path: The full request path
    :param prefix: The path to the servlet root
    :return: The path of the request, relative to the servlet root
    """
    sub_path = full_path[len(prefix) :]
    if not sub_path.startswith("/"):
        sub_path = f"/{sub_path}"

    return _MULTIPLE_SLASHES.sub("/", sub_path)


# ------------------------------------------------------------------------------


@dataclass(frozen=True)
class RequestRouting:
    """
    Result of the routing of an incoming request: the servlet which must handle
    it, if any, and the normalized path it has been routed on.
    """

    path: str
    """ The normalized request path, used both for routing and by the servlet """

    servlet: Any | None
    """ The servlet which must handle the request, or None """

    parameters: dict[str, Any]
    """ The parameters the servlet has been registered with """

    prefix: str
    """ The path the servlet has been registered on """

    servlet_type: http.ServletType
    """ The kind of servlet which must handle the request """


# ------------------------------------------------------------------------------


@Property("_address", http.HTTP_SERVICE_ADDRESS, DEFAULT_BIND_ADDRESS)
@Property("_port", http.HTTP_SERVICE_PORT, 8080)
@Property("_debug_errors", http.HTTP_DEBUG_ERRORS, False)
@Property("_uses_ssl", http.HTTP_USES_SSL, False)
@Property("_cert_file", http.HTTPS_CERT_FILE, None)
@Property("_key_file", http.HTTPS_KEY_FILE, None)
@HiddenProperty("_key_password", http.HTTPS_KEY_PASSWORD, None)
@Property("_extra", HTTP_SERVICE_EXTRA, None)
@Property("_instance_name", constants.IPOPO_INSTANCE_NAME)
@Property("_logger_name", "pelix.http.logger.name", "")
@Property("_logger_level", "pelix.http.logger.level", None)
class AbstractHttpService(http.HTTPService):
    """
    Transport-independent part of the Pelix HTTP service implementations.
    """

    def __init__(self) -> None:
        # Properties
        self._address = DEFAULT_BIND_ADDRESS
        self._port = 8080
        self._debug_errors = False
        self._uses_ssl = False
        self._extra: dict[str, Any] | None = None
        self._instance_name: str | None = None
        self._logger_name: str | None = None
        self._logger_level: str | int | None = None

        # SSL Parameters
        self._cert_file: str | None = None
        self._key_file: str | None = None
        self._key_password: str | None = None

        # Validation flag
        self._validated = False

        # Logger (placeholder until _setup_logger is called)
        self._logger: logging.Logger = logging.getLogger(__name__)

        # Servlets registry lock
        self._lock = threading.RLock()

        # Path -> (servlet, parameters, type)
        self._servlets: dict[str, ServletEntry] = {}

        # Injected by iPOPO in the subclasses
        self._error_handler: http.ErrorHandler | None = None

        # Servlet -> ServiceReference
        self._servlets_refs: dict[AnyServlet, ServiceReference[Any]] = {}
        self._binding_lock = threading.RLock()

    def __str__(self) -> str:
        """
        String representation of the instance
        """
        return f"BasicHttpService({self._address}, {self._port})"

    # --------------------------------------------------------------------------
    # Logging utilities
    # --------------------------------------------------------------------------

    def log(self, level: int, message: str, *args: Any, **kwargs: Any) -> None:
        """
        Logs the given message

        :param level: Log entry level
        :param message: Log message (Python logging format)
        """
        if self._logger is not None:
            # Log the message
            self._logger.log(level, message, *args, **kwargs)

    def log_exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        """
        Logs an exception

        :param message: Log message (Python logging format)
        """
        if self._logger is not None:
            # Log the exception
            self._logger.exception(message, *args, **kwargs)

    # --------------------------------------------------------------------------
    # Configuration
    # --------------------------------------------------------------------------

    def _normalize_configuration(self) -> None:
        """
        Normalizes the values of the properties given to the component: binding
        address, port and extra properties.
        """
        # Check if we'll use an SSL connection
        self._uses_ssl = self._cert_file is not None

        if not self._address:
            # No address given, use the localhost address
            self._address = LOCALHOST_ADDRESS

        if self._port is None:
            # Random port
            self._port = 0
        else:
            # Ensure we have an integer
            self._port = int(self._port)
            # Ensure the port is positive (or set it to 0 for a random port)
            self._port = max(self._port, 0)

        # Normalize the extra properties
        if not isinstance(self._extra, dict):
            self._extra = {}

    def _setup_logger(self) -> logging.Logger:
        """
        Prepares the logger of the component, according to its properties

        :return: The logger to use
        """
        if not self._logger_name:
            # Empty name, use the instance name
            self._logger_name = self._instance_name

        logger = logging.getLogger(self._logger_name)

        level: int | None = None
        if isinstance(self._logger_level, int):
            level = self._logger_level
        elif self._logger_level is not None:
            level = utilities.get_log_level(self._logger_level)
            if level is None:
                try:
                    level = int(self._logger_level)
                except ValueError:
                    # Invalid level
                    level = None

        logger.level = level if level is not None else logging.INFO
        self._logger = logger
        return logger

    # --------------------------------------------------------------------------
    # Server description
    # --------------------------------------------------------------------------

    def get_hostname(self) -> str:
        """
        Retrieves the server host name

        :return: The server host name
        """
        return socket.gethostname()

    def is_https(self) -> bool:
        """
        Returns True if this is an HTTPS server

        :return: True if this server uses SSL
        """
        return self._uses_ssl

    # --------------------------------------------------------------------------
    # Servlets registry
    # --------------------------------------------------------------------------

    def get_registered_paths(self) -> list[str]:
        """
        Returns the paths registered by servlets

        :return: The paths registered by servlets (sorted list)
        """
        return sorted(self._servlets)

    def get_servlet(self, path: str | None) -> tuple[Any, dict[str, Any], str, http.ServletType] | None:
        """
        Retrieves the servlet matching the given path and its parameters.
        Returns None if no servlet matches the given path.

        :param path: A request URI
        :return: A tuple (servlet, parameters, prefix, type) or None
        """
        if not path or path[0] != "/":
            # No path, nothing to return
            return None

        # Use lower case for comparison
        path = path.lower()

        if path[-1] != "/":
            # Add a trailing slash
            path += "/"

        with self._lock:
            longest_match = ""
            longest_match_len = 0
            for servlet_path in self._servlets:
                tested_path = servlet_path
                if tested_path[-1] != "/":
                    # Add a trailing slash
                    tested_path += "/"

                if path.startswith(tested_path) and len(servlet_path) > longest_match_len:
                    # Found a corresponding servlet
                    # which is deeper than the previous one
                    longest_match = servlet_path
                    longest_match_len = len(servlet_path)

            # Return the found servlet
            if not longest_match:
                # No match found
                return None

            # Retrieve the stored information
            servlet, params, servlet_type = self._servlets[longest_match]
            return servlet, params, longest_match, servlet_type

    def resolve_request(self, raw_path: str) -> "RequestRouting":
        """
        Finds the servlet which must handle the request on the given raw path.

        :param raw_path: The raw request path, as given by the client
        :return: The result of the routing (never None). Its ``servlet`` is
                 None if no servlet matches the path.
        """
        normalized_path = normalize_request_path(raw_path)
        found_servlet = self.get_servlet(normalized_path)
        if found_servlet is None:
            return RequestRouting(normalized_path, None, {}, "", http.ServletType.SYNC)

        servlet, params, prefix, servlet_type = found_servlet
        return RequestRouting(normalized_path, servlet, params, prefix, servlet_type)

    def _check_servlet_type(self, servlet_type: http.ServletType) -> None:
        """
        Checks if the given kind of servlet is supported by this implementation.
        Does nothing if it is supported.

        :param servlet_type: The type of servlet to register
        :raise ValueError: The kind of servlet is not supported
        """
        # Everything is supported by default

    def register_servlet(
        self,
        path: str,
        servlet: Any,
        parameters: dict[str, Any] | None = None,
        servlet_type: http.ServletType = http.ServletType.SYNC,
    ) -> bool:
        """
        Registers a servlet

        :param path: Path handled by this servlet
        :param servlet: The servlet instance
        :param parameters: The parameters associated to this path
        :param servlet_type: The type of servlet (sync, async, websocket, ...)
        :return: True if the servlet has been registered, False if it refused the binding.
        :raise ValueError: Invalid path or handler
        """
        self._check_servlet_type(servlet_type)

        if servlet is None:
            raise ValueError("Invalid servlet instance")

        if not path or path[0] != "/":
            raise ValueError(f"Invalid path given to register the servlet: {path}")

        # Use lower-case paths
        path = path.lower()

        # Prepare the parameters
        if parameters is None:
            parameters = {}

        with self._lock:
            if path in self._servlets:
                # Already registered path
                if self._servlets[path][0] is servlet:
                    # Double-registration: Nothing to do
                    return True
                else:
                    # Path is already taken by another servlet
                    already_taken = True
            else:
                # Path is available
                already_taken = False

            # Add server information in parameters
            parameters[http.PARAM_ADDRESS] = self._address
            parameters[http.PARAM_PORT] = self._port
            parameters[http.PARAM_HTTPS] = self._uses_ssl
            parameters[http.PARAM_NAME] = self._instance_name
            parameters[http.PARAM_EXTRA] = self._extra.copy() if self._extra else None
            self._set_extra_parameters(parameters, servlet_type)

            # The servlet might refuse to be bound to this server
            if not self._safe_callback(servlet, "accept_binding", path, parameters):
                # Server refused: stop right there
                # => No need to raise the "already taken path" exception
                return False

            if already_taken:
                # The path is already taken by another servlet
                raise ValueError(f"A servlet is already registered on {path}")

            # Tell the servlet it can be bound to the path
            if self._safe_callback(servlet, "bound_to", path, parameters):
                # Store the servlet
                self._servlets[path] = (servlet, parameters, servlet_type)
                return True

            # The servlet refused the binding
            return False

    def _set_extra_parameters(self, parameters: dict[str, Any], servlet_type: http.ServletType) -> None:
        """
        Adds the implementation-specific entries to the parameters given to a
        servlet when it is bound.

        :param parameters: The parameters given to the servlet
        :param servlet_type: The type of the servlet being registered
        """
        # Nothing to add by default

    def unregister(self, path: str | None, servlet: http.Servlet | None = None) -> bool:
        """
        Unregisters the servlet for the given path

        :param path: The path to a servlet
        :param servlet: If given, unregisters all the paths handled by this servlet
        :return: True if at least one path as been unregistered, else False
        """
        if servlet is not None:
            with self._lock:
                # Unregister all paths for this servlet
                paths = [
                    servlet_path
                    for (servlet_path, servlet_info) in self._servlets.items()
                    if servlet_info[0] == servlet
                ]

            result = False
            for servlet_path in paths:
                result |= self.unregister(servlet_path)

            return result
        else:
            if not path:
                # Invalid path
                return False

            # Always use lower case to compare paths
            path = path.lower()

            with self._lock:
                # Notify the servlet
                servlet_info = self._servlets.get(path)
                if servlet_info is None:
                    # Unknown path
                    return False

                self._safe_callback(servlet_info[0], "unbound_from", path, servlet_info[1])

                # Remove the servlet
                try:
                    del self._servlets[path]
                except KeyError:
                    self.log(logging.DEBUG, "Tried to remove an unknown servlet path: %s", path)
                return True

    # --------------------------------------------------------------------------
    # Error pages
    # --------------------------------------------------------------------------

    def make_not_found_page(self, path: str) -> str:
        """
        Prepares a "page not found" page for a 404 error

        :param path: Request path
        :return: A HTML page
        """
        page = None
        if self._error_handler is not None:
            page = self._error_handler.make_not_found_page(path)

        if not page:
            page = f"""<html>
<head>
<title>404 - Page not found</title>
</head>
<body>
<h1>Page not found</h1>
<p>No servlet is associated to this path:</p>
<code>{html.escape(path)}</code>
<h2>Registered paths:</h2>
{http.make_html_list(self.get_registered_paths())}
</body>
</html>"""
        return page

    def make_exception_page(self, path: str, stack: str) -> str:
        """
        Prepares a page describing an error in a 500 error page.

        The stack trace is only sent to the client if the
        :const:`pelix.http.HTTP_DEBUG_ERRORS` property is set: it gives details
        about the server and about the data it handles. It is always logged,
        along with the error ID shown in the page.

        :param path: Request path
        :param stack: Exception stack trace
        :return: A HTML page
        """
        # Log the details of the error, they are not sent to the client
        error_id = uuid.uuid4().hex
        (self._logger or logging.getLogger(__name__)).error(
            "Error %s handling request upon: %s\n%s", error_id, path, stack
        )

        # Only tell the client how to find the error in the logs
        details = stack if self._debug_errors else f"Error ID: {error_id}"

        page = None
        if self._error_handler is not None:
            page = self._error_handler.make_exception_page(path, details)

        if not page:
            page = f"""<html>
<head>
<title>500 - Internal Server Error</title>
</head>
<body>
<h1>Internal Server Error</h1>
<p>Error handling request upon: <code>{html.escape(path)}</code></p>
<pre>
{html.escape(details)}
</pre>
</body>
</html>"""
        return page

    # --------------------------------------------------------------------------
    # iPOPO bindings
    # --------------------------------------------------------------------------

    def _safe_callback(self, instance: Any, method: str, *args: Any, **kwargs: Any) -> Any:
        """
        Safely calls the given method in the given instance.
        Returns True on method absence.
        Returns False on error.
        Returns the method result if found.

        :param instance: The instance to call
        :param method: The method to call in the instance
        :return: The method result or True on method absence or False on error
        """
        # Call back the method
        if instance is None:
            # Consider invalidity as a failure
            return False

        try:
            callback = getattr(instance, method)
        except AttributeError:
            # Consider absence as a success
            return True

        try:
            result = callback(*args, **kwargs)
            if result is None:
                # Special case: consider None as success
                return True

            return result
        except Exception as ex:
            self.log_exception("Error calling back an instance: %s", ex)

        return False

    def _register_servlet_service(
        self, service: AnyServlet, service_reference: ServiceReference[Any]
    ) -> None:
        """
        Registers a servlet according to its service properties.
        Implemented by the subclasses, as they do not support the same kinds of
        servlet.

        :param service: A servlet service
        :param service_reference: The associated ServiceReference
        """
        raise NotImplementedError

    def _on_bind(self, service: AnyServlet, service_reference: ServiceReference[Any]) -> None:
        """
        A servlet service has been bound

        :param service: A servlet service
        :param service_reference: The associated ServiceReference
        """
        # Ignore imported services
        if self._is_imported(service_reference):
            self.log(logging.DEBUG, "Ignoring service as it is imported: %s", service_reference)
            return

        with self._binding_lock:
            self._servlets_refs[service] = service_reference

            if self._validated:
                # We've been validated, register the service
                self._register_servlet_service(service, service_reference)

    def _on_update(
        self,
        service: AnyServlet,
        service_reference: ServiceReference[Any],
        old_properties: dict[str, Any],
        watched_properties: tuple[str, ...],
    ) -> None:
        """
        The properties of a servlet service have been updated

        :param service: A servlet service
        :param service_reference: The associated ServiceReference
        :param old_properties: The previous properties of the service
        :param watched_properties: Names of the properties which, when modified,
                                   require the servlet to be registered again
        """
        # Ignore imported services
        if self._is_imported(service_reference):
            return

        # Check if the update concerns the registration
        if all(
            old_properties.get(name) == service_reference.get_property(name) for name in watched_properties
        ):
            # Nothing to do
            return

        with self._binding_lock:
            # Unregister the previous paths
            self.unregister(None, cast(http.Servlet, service))

            if self._validated:
                # Register the service with its new properties
                self._register_servlet_service(service, service_reference)

    def _on_unbind(self, service: AnyServlet, service_reference: ServiceReference[Any]) -> None:
        """
        A servlet service is gone

        :param service: A servlet service
        :param service_reference: The associated ServiceReference
        """
        # Ignore imported services
        if self._is_imported(service_reference):
            return

        with self._binding_lock:
            # Servlet gone: unregister all paths associated to this servlet
            self.unregister(None, cast(http.Servlet, service))

            # Remove the service reference
            try:
                del self._servlets_refs[service]
            except KeyError:
                self.log(logging.DEBUG, "Tried to remove an unknown servlet: %s", service)

    def _register_bound_servlets(self) -> None:
        """
        Registers the servlets which have been bound before the component was
        validated. Must be called once the server is ready.
        """
        with self._binding_lock:
            # Set the validation flag up, once the server is ready
            self._validated = True

            # Register bound servlets
            for service, svc_ref in self._servlets_refs.items():
                self._register_servlet_service(service, svc_ref)

    def _unregister_all_servlets(self) -> None:
        """
        Refuses new registrations and unregisters all the bound servlets, to
        notify them with ``unbound_from``.
        """
        with self._binding_lock:
            # Refuse new registrations
            self._validated = False

            # Unregister servlets (to call unbound_from...)
            for service in self._servlets_refs:
                self.unregister(None, cast(http.Servlet, service))

    @staticmethod
    def _is_imported(service_reference: ServiceReference[Any]) -> bool:
        """
        Tests if the given service has been imported by Remote Services

        :param service_reference: The reference of the service to check
        :return: True if the service is flagged as imported
        """
        return cast(bool, service_reference.get_property(pelix.remote.PROP_IMPORTED))
