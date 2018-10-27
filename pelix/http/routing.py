#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Provides utility classes to develop REST-like API and to simplify the routing
of HTTP requests.

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
import inspect
import re
import uuid

# Standard typing module should be optional
try:
    # pylint: disable=W0611
    from typing import Any, Callable, Dict, Pattern, Tuple
    from pelix.http import (
        AbstractHTTPServletRequest,
        AbstractHTTPServletResponse,
    )
except ImportError:
    pass

# Pelix utility methods
from pelix.utilities import get_method_arguments

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

HTTP_ROUTE_ATTRIBUTE = "__pelix_http_route__"
"""
Name of the attribute injected in methods to indicate their configuration
"""

# Same types as in Flask:
# string 	accepts any text without a slash (the default)
# int 	    accepts integers
# float 	like int but for floating point values
# path 	    like the default but also accepts slashes
# uuid 	    accepts UUID strings

# TODO: handle missing types
# any 	    matches one of the items provided

# Type name -> regex pattern
TYPE_PATTERNS = {
    "string": r"(?:[^/]+)",
    "int": r"(?:[+\-]?\d+)",
    "float": r"(?:[+\-]?\d+\.?\d*)",
    "path": r"(?:[\w\s/]+)",
    "uuid": r"(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
    r"-[0-9a-fA-F]{12})",
}
TYPE_PATTERNS[None] = TYPE_PATTERNS["string"]


# Constant patterns
_MARKER_PATTERN = re.compile(r"<[^<>]*>")
_TYPED_MARKER_PATTERN = re.compile(r"<(\w+):?(\w+)?>")


def path_filter(path):
    # type: (str) -> str
    """
    Removes the trailing '/' of a path, if any

    :param path: A parsed path
    :return: The parsed path without its trailing /
    """
    return path[:-1] if path and path[-1] == "/" else path


# Type name -> conversion method (for types other than str)
TYPE_CONVERTERS = {
    "int": int,
    "float": float,
    "path": path_filter,
    "uuid": uuid.UUID,
}  # type: Dict[str, Callable[[str], Any]]

# ------------------------------------------------------------------------------


class Http(object):
    """
    Decorator indicating which route a method handles
    """

    def __init__(self, route, methods=None):
        """
        :param route: Path handled by the method (beginning with a '/')
        :param methods: List of HTTP methods allowed (GET, POST, ...)
        """
        if not route:
            # Normalize route
            route = "/"
        else:
            # Remove surrounding spaces
            route = route.strip()

        if methods and not isinstance(methods, (list, tuple, set, frozenset)):
            # Normalize methods
            raise TypeError("methods should be a list")

        self._route = route
        self._methods = methods or ["GET"]

    def __call__(self, decorated_method):
        """
        Injects the HTTP_ROUTE_ATTRIBUTE to the decorated method to store the
        description of the route

        :param decorated_method: The decorated method
        """
        if not inspect.isroutine(decorated_method):
            raise TypeError(
                "@Http can decorate only methods, not {0}".format(
                    type(decorated_method).__name__
                )
            )

        try:
            config = getattr(decorated_method, HTTP_ROUTE_ATTRIBUTE)
        except AttributeError:
            config = {}
            setattr(decorated_method, HTTP_ROUTE_ATTRIBUTE, config)

        # Use sets to avoid duplications
        config.setdefault("routes", set()).add(self._route)
        config.setdefault("methods", set()).update(self._methods)
        return decorated_method


class HttpGet(Http):
    """
    Decorates a method handling GET requests
    """

    def __init__(self, route):
        """
        :param route: Path handled by the method (beginning with a '/')
        """
        super(HttpGet, self).__init__(route, methods=["GET"])


class HttpHead(Http):
    """
    Decorates a method handling HEAD requests
    """

    def __init__(self, route):
        """
        :param route: Path handled by the method (beginning with a '/')
        """
        super(HttpHead, self).__init__(route, methods=["HEAD"])


class HttpPost(Http):
    """
    Decorates a method handling POST requests
    """

    def __init__(self, route):
        """
        :param route: Path handled by the method (beginning with a '/')
        """
        super(HttpPost, self).__init__(route, methods=["POST"])


class HttpPut(Http):
    """
    Decorates a method handling PUT requests
    """

    def __init__(self, route):
        """
        :param route: Path handled by the method (beginning with a '/')
        """
        super(HttpPut, self).__init__(route, methods=["PUT"])


class HttpDelete(Http):
    """
    Decorates a method handling DELETE requests
    """

    def __init__(self, route):
        """
        :param route: Path handled by the method (beginning with a '/')
        """
        super(HttpDelete, self).__init__(route, methods=["DELETE"])


# ------------------------------------------------------------------------------


class RestDispatcher(object):
    """
    Parent class for servlets: dispatches requests according to the @Http
    decorator
    """

    def __init__(self):
        """
        Looks for the methods where to dispatch requests
        """
        # HTTP verb -> route pattern -> function
        self.__routes = {}

        # function -> arg name -> arg converter
        self.__methods_args = {}

        # Find all REST methods
        self._setup_rest_dispatcher()

    def do_GET(self, request, response):
        # pylint: disable=C0103
        """
        Handles a GET request
        """
        self._rest_dispatch(request, response)

    def do_HEAD(self, request, response):
        # pylint: disable=C0103
        """
        Handles a HEAD request
        """
        self._rest_dispatch(request, response)

    def do_POST(self, request, response):
        # pylint: disable=C0103
        """
        Handles a POST request
        """
        self._rest_dispatch(request, response)

    def do_PUT(self, request, response):
        # pylint: disable=C0103
        """
        Handles a PUT request
        """
        self._rest_dispatch(request, response)

    def do_DELETE(self, request, response):
        # pylint: disable=C0103
        """
        Handles a DELETE request
        """
        self._rest_dispatch(request, response)

    def _rest_dispatch(self, request, response):
        # type: (AbstractHTTPServletRequest, AbstractHTTPServletResponse) -> None
        """
        Dispatches the request

        :param request: Request bean
        :param response: Response bean
        """
        # Extract request information
        http_verb = request.get_command()
        sub_path = request.get_sub_path()

        # Find the best matching method, according to the number of
        # readable arguments
        max_valid_args = -1
        best_method = None
        best_args = None
        best_match = None

        for route, method in self.__routes.get(http_verb, {}).items():
            # Parse the request path
            match = route.match(sub_path)
            if not match:
                continue

            # Count the number of valid arguments
            method_args = self.__methods_args[method]
            nb_valid_args = 0
            for name in method_args:
                try:
                    match.group(name)
                    nb_valid_args += 1
                except IndexError:
                    # Argument not found
                    pass

            if nb_valid_args > max_valid_args:
                # Found a better match
                max_valid_args = nb_valid_args
                best_method = method
                best_args = method_args
                best_match = match

        if best_method is None:
            # No match: return a 404 plain text error
            response.send_content(
                404,
                "No method to handle path {0}".format(sub_path),
                "text/plain",
            )
        else:
            # Found a method
            # ... convert arguments
            kwargs = {}
            if best_args:
                for name, converter in best_args.items():
                    try:
                        str_value = best_match.group(name)
                    except IndexError:
                        # Argument is missing: do nothing
                        pass
                    else:
                        if str_value:
                            # Keep the default value when an argument is
                            # missing, i.e. don't give it in kwargs
                            if converter is not None:
                                # Convert the argument
                                kwargs[name] = converter(str_value)
                            else:
                                # Use the string value as is
                                kwargs[name] = str_value

            # Prepare positional arguments
            extra_pos_args = []
            if kwargs:
                # Ignore the first two parameters (request and response)
                method_args = get_method_arguments(best_method).args[:2]
                for pos_arg in method_args:
                    try:
                        extra_pos_args.append(kwargs.pop(pos_arg))
                    except KeyError:
                        pass

            # ... call the method (exceptions will be handled by the server)
            best_method(request, response, *extra_pos_args, **kwargs)

    def _setup_rest_dispatcher(self):
        """
        Finds all methods to call when handling a route
        """
        for _, method in inspect.getmembers(self, inspect.isroutine):
            try:
                config = getattr(method, HTTP_ROUTE_ATTRIBUTE)
            except AttributeError:
                # Not a REST method
                continue

            for route in config["routes"]:
                pattern, arguments = self.__convert_route(route)
                self.__methods_args.setdefault(method, {}).update(arguments)
                for http_verb in config["methods"]:
                    self.__routes.setdefault(http_verb, {})[pattern] = method

    @staticmethod
    def __convert_route(route):
        # type: (str) -> Tuple[Pattern[str], Dict[str, Callable[[str], Any]]]
        """
        Converts a route pattern into a regex.
        The result is a tuple containing the regex pattern to match and a
        dictionary associating arguments names and their converter (if any)

        A route can be: "/hello/<name>/<age:int>"

        :param route: A route string, i.e. a path with type markers
        :return: A tuple (pattern, {argument name: converter})
        """
        arguments = {}  # type: Dict[str, Callable[[str], Any]]
        last_idx = 0
        final_pattern = []
        match_iter = _MARKER_PATTERN.finditer(route)
        for match_pattern in match_iter:
            # Copy intermediate string
            final_pattern.append(route[last_idx : match_pattern.start()])
            last_idx = match_pattern.end() + 1

            # Extract type declaration
            match_type = _TYPED_MARKER_PATTERN.match(match_pattern.group())
            if not match_type:
                raise ValueError(
                    "Invalid argument declaration: {0}".format(
                        match_pattern.group()
                    )
                )

            name, kind = match_type.groups()
            if kind:
                kind = kind.lower()

            # Choose a pattern for each type (can raise a KeyError)
            regex = TYPE_PATTERNS[kind]

            # Keep track of argument name and converter
            arguments[name] = TYPE_CONVERTERS.get(kind)

            # Generate the regex pattern for this part
            final_pattern.append("((?P<")
            final_pattern.append(match_type.group(1))
            final_pattern.append(">")
            final_pattern.append(regex)
            final_pattern.append(")/?)?")

        # Copy trailing string
        final_pattern.append(route[last_idx:])

        # Ensure we don't accept trailing values
        final_pattern.append("$")
        return re.compile("".join(final_pattern)), arguments
