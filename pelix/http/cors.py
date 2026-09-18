#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Cross-Origin Resource Sharing (CORS) support for the Pelix HTTP services.

Provides the computation of the CORS headers shared by the HTTP service
implementations, a static CORS policy and a component factory to configure it
with properties.

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 3.2.3

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

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pelix import http
from pelix.ipopo.decorators import ComponentFactory, Property, Provides

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 2, 3)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = [
    "ANY_ORIGIN",
    "SERVLET_CORS_PARAMETERS",
    "CorsDecision",
    "CorsHandlerComponent",
    "StaticCorsHandler",
    "compute_cors_headers",
    "policy_from_parameters",
    "resolve_cors",
]

# ------------------------------------------------------------------------------

ANY_ORIGIN = "*"
""" Value of an allowed origin matching any origin """

SERVLET_CORS_PARAMETERS = (
    http.HTTP_CORS_ORIGINS,
    http.HTTP_CORS_METHODS,
    http.HTTP_CORS_HEADERS,
    http.HTTP_CORS_EXPOSE_HEADERS,
    http.HTTP_CORS_CREDENTIALS,
    http.HTTP_CORS_MAX_AGE,
)
""" Servlet service properties describing its own CORS policy """

# ------------------------------------------------------------------------------


def _to_list(value: Any) -> list[str] | None:
    """
    Normalizes a configuration value into a list of strings

    :param value: None, a (comma-separated) string or an iterable of strings
    :return: A list of non-empty strings, or None if the value is None
    """
    if value is None:
        return None

    if isinstance(value, str):
        value = value.split(",")

    return [item for item in (str(raw).strip() for raw in value) if item]


def _to_bool(value: Any) -> bool:
    """
    Normalizes a boolean configuration value, which can be given as a string

    :param value: The raw value
    :return: The boolean value
    """
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")

    return bool(value)


def _to_max_age(value: Any) -> int | None:
    """
    Normalizes the maximum age of a preflight result

    :param value: The raw value
    :return: A positive or zero number of seconds, or None
    """
    if value is None:
        return None

    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return None


class StaticCorsHandler(http.CorsHandler):
    """
    A CORS policy which is the same for all paths
    """

    def __init__(
        self,
        origins: str | Iterable[str] | None = None,
        methods: str | Iterable[str] | None = None,
        headers: str | Iterable[str] | None = None,
        expose_headers: str | Iterable[str] | None = None,
        credentials: bool = False,
        max_age: int | None = None,
    ) -> None:
        """
        :param origins: Allowed origins (``*`` for any, nothing for none)
        :param methods: Allowed methods (None to allow the requested one)
        :param headers: Allowed request headers (None to allow the requested ones)
        :param expose_headers: Response headers readable by the client
        :param credentials: If True, the requests can carry credentials
        :param max_age: Time a client can cache a preflight result
        """
        self._origins = _to_list(origins) or []
        methods_list = _to_list(methods)
        self._methods = [method.upper() for method in methods_list] if methods_list is not None else None
        self._headers = _to_list(headers)
        self._expose_headers = _to_list(expose_headers)
        self._credentials = _to_bool(credentials)
        self._max_age = _to_max_age(max_age)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(origins={self._origins!r}, credentials={self._credentials})"

    @classmethod
    def from_properties(cls, properties: Mapping[str, Any]) -> "StaticCorsHandler":
        """
        Creates a policy from the ``pelix.http.cors.*`` entries of the given
        properties

        :param properties: Service properties or servlet parameters
        :return: The CORS policy they describe
        """
        return cls(
            properties.get(http.HTTP_CORS_ORIGINS),
            properties.get(http.HTTP_CORS_METHODS),
            properties.get(http.HTTP_CORS_HEADERS),
            properties.get(http.HTTP_CORS_EXPOSE_HEADERS),
            properties.get(http.HTTP_CORS_CREDENTIALS, False),
            properties.get(http.HTTP_CORS_MAX_AGE),
        )

    def get_allowed_origins(self, path: str) -> Iterable[str]:
        return self._origins

    def get_allowed_methods(self, path: str) -> Iterable[str] | None:
        return self._methods

    def get_allowed_headers(self, path: str) -> Iterable[str] | None:
        return self._headers

    def get_exposed_headers(self, path: str) -> Iterable[str] | None:
        return self._expose_headers

    def allows_credentials(self, path: str) -> bool:
        return self._credentials

    def get_max_age(self, path: str) -> int | None:
        return self._max_age


@ComponentFactory(http.FACTORY_HTTP_CORS)
@Provides(http.CorsHandler)
@Property("_origins", http.HTTP_CORS_ORIGINS, None)
@Property("_methods", http.HTTP_CORS_METHODS, None)
@Property("_headers", http.HTTP_CORS_HEADERS, None)
@Property("_expose_headers", http.HTTP_CORS_EXPOSE_HEADERS, None)
@Property("_credentials", http.HTTP_CORS_CREDENTIALS, False)
@Property("_max_age", http.HTTP_CORS_MAX_AGE, None)
class CorsHandlerComponent(http.CorsHandler):
    """
    CORS handler service configured with the ``pelix.http.cors.*`` properties
    of the component instance.
    """

    def __init__(self) -> None:
        self._origins: str | list[str] | None = None
        self._methods: str | list[str] | None = None
        self._headers: str | list[str] | None = None
        self._expose_headers: str | list[str] | None = None
        self._credentials: bool = False
        self._max_age: int | None = None

    def __policy(self) -> StaticCorsHandler:
        """
        Computes the policy from the current values of the properties.

        This is done on each call rather than on validation, so that the
        properties can be updated at runtime.
        """
        return StaticCorsHandler(
            self._origins,
            self._methods,
            self._headers,
            self._expose_headers,
            self._credentials,
            self._max_age,
        )

    def get_allowed_origins(self, path: str) -> Iterable[str]:
        return self.__policy().get_allowed_origins(path)

    def get_allowed_methods(self, path: str) -> Iterable[str] | None:
        return self.__policy().get_allowed_methods(path)

    def get_allowed_headers(self, path: str) -> Iterable[str] | None:
        return self.__policy().get_allowed_headers(path)

    def get_exposed_headers(self, path: str) -> Iterable[str] | None:
        return self.__policy().get_exposed_headers(path)

    def allows_credentials(self, path: str) -> bool:
        return self.__policy().allows_credentials(path)

    def get_max_age(self, path: str) -> int | None:
        return self.__policy().get_max_age(path)


# ------------------------------------------------------------------------------


def policy_from_parameters(parameters: Mapping[str, Any]) -> StaticCorsHandler | None:
    """
    Returns the CORS policy declared by a servlet in its registration
    parameters, if any.

    A servlet declares its own policy by setting the
    ``pelix.http.cors.origins`` property; the other CORS properties are ignored
    without it.

    :param parameters: The parameters of a servlet registration
    :return: The CORS policy of the servlet, or None
    """
    if parameters.get(http.HTTP_CORS_ORIGINS) is None:
        return None

    return StaticCorsHandler.from_properties(parameters)


def compute_cors_headers(
    policy: http.CorsHandler,
    path: str,
    origin: str,
    preflight: bool = False,
    request_method: str | None = None,
    request_headers: str | None = None,
) -> dict[str, str] | None:
    """
    Computes the CORS headers to send in the response to a cross-origin
    request

    :param policy: The CORS policy to apply
    :param path: The normalized request path
    :param origin: The value of the ``Origin`` request header
    :param preflight: True if the request is a preflight request
    :param request_method: Value of the ``Access-Control-Request-Method`` header
    :param request_headers: Value of the ``Access-Control-Request-Headers`` header
    :return: The headers to add to the response, or None if the request is
             refused by the policy
    """
    origins = set(policy.get_allowed_origins(path) or ())
    any_origin = ANY_ORIGIN in origins
    if not any_origin and origin not in origins:
        return None

    credentials = policy.allows_credentials(path)

    headers: dict[str, str] = {}
    if any_origin and not credentials:
        headers["Access-Control-Allow-Origin"] = ANY_ORIGIN
    else:
        # Browsers refuse credentials with a wildcard: send the origin back,
        # and tell caches the response depends on it
        headers["Access-Control-Allow-Origin"] = origin
        headers["Vary"] = "Origin"

    if credentials:
        headers["Access-Control-Allow-Credentials"] = "true"

    if preflight:
        methods = policy.get_allowed_methods(path)
        if methods is not None:
            methods = [method.upper() for method in methods]
            if request_method and request_method.upper() not in methods:
                return None
        elif request_method:
            methods = [request_method.upper()]

        if methods:
            headers["Access-Control-Allow-Methods"] = ", ".join(methods)

        allowed_headers = policy.get_allowed_headers(path)
        if allowed_headers is not None:
            if allowed_headers:
                headers["Access-Control-Allow-Headers"] = ", ".join(allowed_headers)
        elif request_headers:
            headers["Access-Control-Allow-Headers"] = request_headers

        max_age = policy.get_max_age(path)
        if max_age is not None:
            headers["Access-Control-Max-Age"] = str(max_age)
    else:
        exposed = policy.get_exposed_headers(path)
        if exposed:
            headers["Access-Control-Expose-Headers"] = ", ".join(exposed)

    return headers


@dataclass(frozen=True)
class CorsDecision:
    """
    What a HTTP service must do with a cross-origin request
    """

    preflight: bool
    """ True if the request is a preflight request, to be answered directly """

    headers: dict[str, str] | None
    """ Headers to add to the response, or None if the request is refused """

    @property
    def allowed(self) -> bool:
        """
        True if the request is allowed by the CORS policy
        """
        return self.headers is not None


def resolve_cors(
    policy: http.CorsHandler | None,
    path: str,
    method: str,
    origin: str | None,
    request_method: str | None,
    request_headers: str | None,
) -> CorsDecision | None:
    """
    Decides how to handle a request according to a CORS policy

    :param policy: The CORS policy to apply, or None
    :param path: The normalized request path
    :param method: The HTTP method of the request
    :param origin: The value of the ``Origin`` request header, if any
    :param request_method: Value of the ``Access-Control-Request-Method`` header
    :param request_headers: Value of the ``Access-Control-Request-Headers`` header
    :return: None if CORS doesn't apply to this request, else the decision
    """
    if policy is None or not origin:
        # Not a cross-origin request, or no policy: the request is handled as usual
        return None

    # A preflight is an OPTIONS request announcing the method of the real one
    preflight = method.upper() == "OPTIONS" and bool(request_method)
    headers = compute_cors_headers(policy, path, origin, preflight, request_method, request_headers)
    return CorsDecision(preflight, headers)
