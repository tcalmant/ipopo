#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: XML-RPC client transports applying the client limits

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 3.3.0

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

import http.client
import io
import xmlrpc.client as xmlrpclib
from typing import Any

from pelix.remote.transport.commons import ClientLimits, read_response

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = ["LimitedTransportMixIn", "make_client_transport"]

# ------------------------------------------------------------------------------


class LimitedTransportMixIn(xmlrpclib.Transport):
    """
    Applies the client limits to a transport based on the one of ``xmlrpc.client``
    """

    def __init__(self, limits: ClientLimits, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._limits = limits

        # A compressed response could be expanded beyond the maximum size
        self.accept_gzip_encoding = False

    def make_connection(self, host: Any) -> Any:
        connection = super().make_connection(host)
        connection.timeout = self._limits.timeout
        return connection

    def parse_response(self, response: http.client.HTTPResponse) -> Any:
        # A plain stream also prevents the parent class from decompressing the body
        body = io.BytesIO(read_response(response, self._limits.max_size))
        return super().parse_response(body)  # ty: ignore[invalid-argument-type]


class _XmlRpcTransport(LimitedTransportMixIn, xmlrpclib.Transport):
    pass


class _XmlRpcSafeTransport(LimitedTransportMixIn, xmlrpclib.SafeTransport):
    pass


def make_client_transport(url: str, limits: ClientLimits) -> xmlrpclib.Transport:
    """
    Prepares the transport of an XML-RPC server proxy, applying the client limits

    :param url: URL of the server
    :param limits: The client limits
    :return: A transport for the ``ServerProxy`` of ``xmlrpc.client``
    """
    return (_XmlRpcSafeTransport if url.lower().startswith("https:") else _XmlRpcTransport)(limits)
