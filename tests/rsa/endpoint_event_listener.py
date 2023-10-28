#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests using the RSA EndpointEventListener callback service

:author: slewis
"""

from threading import RLock

from pelix.ipopo.decorators import ComponentFactory, Provides
from pelix.rsa.providers.discovery import SERVICE_ENDPOINT_LISTENER,\
    EndpointEventListener

__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)


@ComponentFactory("etcd-test-endpoint-event-listener-factory")
@Provides(
    [
        SERVICE_ENDPOINT_LISTENER
    ]
)
class TestEndpointEventListener(EndpointEventListener):

    def __init__(self):
        self._func = None
        self._lock = RLock()

    def endpoint_changed(self, endpoint_event, matched_filter):
        with self._lock:
            if self._func:
                self._func(endpoint_event, matched_filter)
            else:
                print("TestEndpointEventListener.endpoint_changed endpoint_event={0},matched_filter={1}".
                      format(endpoint_event, matched_filter))

    def set_handler(self, func):
        with self._lock:
            self._func = func
