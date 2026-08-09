#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the resource limits of the basic HTTP service: body size, socket timeout
and lifecycle of the request handling threads.

:author: Thomas Calmant
"""

import importlib.util
import socket
import threading
import time
import unittest
from typing import Any, cast

from pelix import http
from pelix.framework import Framework, FrameworkFactory, create_framework
from pelix.ipopo.constants import IPopoService
from tests.http.utils import DEFAULT_HOST, install_ipopo

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Name of the request handling threads of the basic HTTP service
THREAD_NAME_PREFIX = "HttpService-"

# ------------------------------------------------------------------------------


class EchoServlet:
    """
    Servlet which answers the size of the body it received
    """

    def __init__(self) -> None:
        self.bodies: list[bytes] = []

    def do_POST(self, request: http.AbstractHTTPServletRequest, response: Any) -> None:
        """
        Reads the body of the request and answers its size
        """
        data = request.read_data()
        self.bodies.append(data)
        response.send_content(200, str(len(data)), "text/plain")


class AsyncEchoServlet:
    """
    Asynchronous servlet which answers the size of the body it received
    """

    def __init__(self) -> None:
        self.bodies: list[bytes] = []

    async def do_async_POST(
        self, request: http.AbstractAsyncHTTPServletRequest, response: http.AbstractAsyncHTTPServletResponse
    ) -> None:
        """
        Reads the body of the request and answers its size
        """
        data = await request.read_data()
        self.bodies.append(data)
        await response.send_content(200, str(len(data)), "text/plain")


def list_request_threads() -> list[str]:
    """
    Returns the names of the request handling threads which are still alive
    """
    return [thread.name for thread in threading.enumerate() if thread.name.startswith(THREAD_NAME_PREFIX)]


class BodyLimitsTest(unittest.TestCase):
    """
    Tests the handling of the body of the requests
    """

    framework: Framework
    ipopo: IPopoService

    http_bundle = "pelix.http.basic"
    http_factory = http.FACTORY_HTTP_BASIC

    def setUp(self) -> None:
        """
        Prepares a framework with the HTTP service under test
        """
        self.framework = create_framework([])
        self.framework.start()
        self.ipopo = install_ipopo(self.framework)
        self.servlet = EchoServlet()

        context = self.framework.get_bundle_context()
        context.install_bundle(self.http_bundle).start()

    def tearDown(self) -> None:
        """
        Cleans up for the next test
        """
        FrameworkFactory.delete_framework(self.framework)
        self.framework = None  # type: ignore

    def start_server(self, **properties: Any) -> http.HTTPService:
        """
        Starts the HTTP service on a random port and registers the echo servlet

        :param properties: Extra properties for the HTTP service component
        :return: The HTTP service
        """
        service = cast(
            http.HTTPService,
            self.ipopo.instantiate(
                self.http_factory,
                "test-http-limits",
                {http.HTTP_SERVICE_ADDRESS: DEFAULT_HOST, http.HTTP_SERVICE_PORT: 0, **properties},
            ),
        )

        context = self.framework.get_bundle_context()
        context.register_service(http.HTTP_SERVLET, self.servlet, {http.HTTP_SERVLET_PATH: "/echo"})
        return service

    def request(self, port: int, raw: bytes, timeout: float = 10.0) -> bytes:
        """
        Sends a raw request to the server and returns its answer

        :param port: Port of the server
        :param raw: Raw request to send
        :param timeout: Maximum time to wait for the answer
        :return: The raw answer of the server
        """
        with socket.create_connection((DEFAULT_HOST, port), timeout=timeout) as sock:
            sock.sendall(raw)

            chunks = []
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)

        return b"".join(chunks)

    def test_no_content_length(self) -> None:
        """
        A POST without Content-Length must be answered immediately, with an
        empty body, instead of blocking the handling thread until the client
        goes away
        """
        port = self.start_server().get_access()[1]

        start = time.monotonic()
        answer = self.request(port, b"POST /echo HTTP/1.0\r\nHost: localhost\r\n\r\n", timeout=10.0)
        duration = time.monotonic() - start

        self.assertIn(b"200", answer.splitlines()[0])
        self.assertLess(duration, 5.0, "The request took too long to be handled")

        # The body must have been considered empty, not read until EOF
        self.assertEqual(self.servlet.bodies, [b""])

    def test_invalid_content_length(self) -> None:
        """
        An unparsable Content-Length is handled like a missing one
        """
        port = self.start_server().get_access()[1]

        answer = self.request(
            port, b"POST /echo HTTP/1.0\r\nHost: localhost\r\nContent-Length: abc\r\n\r\nhello"
        )
        self.assertIn(b"200", answer.splitlines()[0])
        self.assertEqual(self.servlet.bodies, [b""])

    def test_body_too_large(self) -> None:
        """
        A body bigger than pelix.http.max_body_size is refused with a 413 error
        """
        port = self.start_server(**{http.HTTP_MAX_BODY_SIZE: 100}).get_access()[1]

        body = b"x" * 200
        answer = self.request(
            port,
            b"POST /echo HTTP/1.0\r\nHost: localhost\r\nContent-Length: 200\r\n\r\n" + body,
        )

        self.assertIn(b"413", answer.splitlines()[0])
        self.assertListEqual(self.servlet.bodies, [], "The body should not have been read")

    def test_body_at_the_limit(self) -> None:
        """
        A body of exactly pelix.http.max_body_size bytes is accepted and read
        completely
        """
        port = self.start_server(**{http.HTTP_MAX_BODY_SIZE: 100}).get_access()[1]

        body = b"x" * 100
        answer = self.request(
            port,
            b"POST /echo HTTP/1.0\r\nHost: localhost\r\nContent-Length: 100\r\n\r\n" + body,
        )

        self.assertIn(b"200", answer.splitlines()[0])
        self.assertListEqual(self.servlet.bodies, [body])

    def test_socket_timeout(self) -> None:
        """
        A client which announces a body it never sends must not keep a handling
        thread busy longer than pelix.http.socket_timeout
        """
        port = self.start_server(**{http.HTTP_SOCKET_TIMEOUT: 1}).get_access()[1]

        # Announce 500 bytes, send only 10 of them
        start = time.monotonic()
        answer = self.request(
            port,
            b"POST /echo HTTP/1.0\r\nHost: localhost\r\nContent-Length: 500\r\n\r\n0123456789",
            timeout=30.0,
        )
        duration = time.monotonic() - start

        self.assertIn(b"408", answer.splitlines()[0])
        self.assertLess(duration, 15.0, "The server waited longer than its timeout")
        self.assertListEqual(self.servlet.bodies, [])

    def test_no_socket_timeout(self) -> None:
        """
        A non-positive pelix.http.socket_timeout removes the timeout
        """
        service = self.start_server(**{http.HTTP_SOCKET_TIMEOUT: 0})
        self.assertIsNone(cast(Any, service).get_socket_timeout())

        # A regular request must still be handled
        port = service.get_access()[1]
        answer = self.request(port, b"POST /echo HTTP/1.0\r\nHost: localhost\r\nContent-Length: 2\r\n\r\nok")
        self.assertIn(b"200", answer.splitlines()[0])
        self.assertListEqual(self.servlet.bodies, [b"ok"])

    def test_no_limit(self) -> None:
        """
        A non-positive pelix.http.max_body_size removes the limit
        """
        port = self.start_server(**{http.HTTP_MAX_BODY_SIZE: 0}).get_access()[1]

        body = b"x" * 4096
        answer = self.request(
            port,
            b"POST /echo HTTP/1.0\r\nHost: localhost\r\nContent-Length: 4096\r\n\r\n" + body,
        )

        self.assertIn(b"200", answer.splitlines()[0])
        self.assertListEqual(self.servlet.bodies, [body])


@unittest.skipIf(importlib.util.find_spec("aiohttp") is None, "aiohttp library not available")
class AsyncBodyLimitsTest(BodyLimitsTest):
    """
    Tests the body size limit of the asynchronous HTTP service, where it is
    enforced by aiohttp itself
    """

    http_bundle = "pelix.http.basic_async"
    http_factory = http.FACTORY_HTTP_ASYNC

    @unittest.skip("The asynchronous server relies on its own socket timeouts")
    def test_socket_timeout(self) -> None:
        pass

    @unittest.skip("The asynchronous server relies on its own socket timeouts")
    def test_no_socket_timeout(self) -> None:
        pass

    @unittest.skip("A missing content length means a chunked body for aiohttp")
    def test_no_content_length(self) -> None:
        pass

    @unittest.skip("A missing content length means a chunked body for aiohttp")
    def test_invalid_content_length(self) -> None:
        pass


class PerServletLimitsTest(unittest.TestCase):
    """
    Tests the pelix.http.max_body_size property given by a servlet, which
    overrides the one of the HTTP service
    """

    framework: Framework
    ipopo: IPopoService

    http_bundle = "pelix.http.basic"
    http_factory = http.FACTORY_HTTP_BASIC

    # Limit of the HTTP service in those tests
    SERVICE_LIMIT = 100

    def setUp(self) -> None:
        """
        Prepares a framework with an HTTP service limiting the bodies to
        SERVICE_LIMIT bytes
        """
        self.framework = create_framework([])
        self.framework.start()
        self.ipopo = install_ipopo(self.framework)

        self.context = self.framework.get_bundle_context()
        self.context.install_bundle(self.http_bundle).start()

        self.service = cast(
            http.HTTPService,
            self.ipopo.instantiate(
                self.http_factory,
                "test-http-servlet-limits",
                {
                    http.HTTP_SERVICE_ADDRESS: DEFAULT_HOST,
                    http.HTTP_SERVICE_PORT: 0,
                    http.HTTP_MAX_BODY_SIZE: self.SERVICE_LIMIT,
                },
            ),
        )
        self.port = self.service.get_access()[1]

    def tearDown(self) -> None:
        """
        Cleans up for the next test
        """
        FrameworkFactory.delete_framework(self.framework)
        self.framework = None  # type: ignore

    def post(self, path: str, size: int) -> tuple[bytes, bytes]:
        """
        Posts a body of the given size to the given path

        :param path: Path of the servlet
        :param size: Size of the body to send
        :return: The status line and the body of the answer
        """
        body = b"x" * size
        raw = f"POST {path} HTTP/1.0\r\nHost: localhost\r\nContent-Length: {size}\r\n\r\n".encode() + body

        with socket.create_connection((DEFAULT_HOST, self.port), timeout=10.0) as sock:
            sock.sendall(raw)

            chunks = []
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)

        answer = b"".join(chunks)
        return answer.splitlines()[0], answer

    def test_servlet_raises_the_limit(self) -> None:
        """
        A servlet can accept bodies bigger than the ones accepted by the HTTP
        service, without affecting the other servlets
        """
        large = EchoServlet()
        self.context.register_service(
            http.HTTP_SERVLET,
            large,
            {http.HTTP_SERVLET_PATH: "/large", http.HTTP_MAX_BODY_SIZE: 4096},
        )

        default = EchoServlet()
        self.context.register_service(http.HTTP_SERVLET, default, {http.HTTP_SERVLET_PATH: "/default"})

        # The servlet with a bigger limit accepts the body...
        status, _ = self.post("/large", 1000)
        self.assertIn(b"200", status)
        self.assertEqual([len(body) for body in large.bodies], [1000])

        # ... and the limit of the service still applies to the other one
        status, _ = self.post("/default", 1000)
        self.assertIn(b"413", status)
        self.assertListEqual(default.bodies, [])

    def test_servlet_lowers_the_limit(self) -> None:
        """
        A servlet can refuse bodies accepted by the HTTP service
        """
        small = EchoServlet()
        self.context.register_service(
            http.HTTP_SERVLET,
            small,
            {http.HTTP_SERVLET_PATH: "/small", http.HTTP_MAX_BODY_SIZE: 10},
        )

        # Under the limit of the service, over the one of the servlet
        status, _ = self.post("/small", 50)
        self.assertIn(b"413", status)
        self.assertListEqual(small.bodies, [])

        # Under both limits
        status, _ = self.post("/small", 5)
        self.assertIn(b"200", status)
        self.assertEqual([len(body) for body in small.bodies], [5])

    def test_register_servlet_parameters(self) -> None:
        """
        The limit can also be given in the parameters of register_servlet(),
        without using the whiteboard pattern
        """
        servlet = EchoServlet()
        self.service.register_servlet("/direct", servlet, {http.HTTP_MAX_BODY_SIZE: 4096})

        status, _ = self.post("/direct", 1000)
        self.assertIn(b"200", status)
        self.assertEqual([len(body) for body in servlet.bodies], [1000])

    def test_property_update(self) -> None:
        """
        Updating the property of a registered servlet service updates the limit
        """
        servlet = EchoServlet()
        registration = self.context.register_service(
            http.HTTP_SERVLET, servlet, {http.HTTP_SERVLET_PATH: "/updated"}
        )

        # The limit of the service applies
        status, _ = self.post("/updated", 1000)
        self.assertIn(b"413", status)

        # Raise the limit of the servlet
        registration.set_properties({http.HTTP_SERVLET_PATH: "/updated", http.HTTP_MAX_BODY_SIZE: 4096})

        status, _ = self.post("/updated", 1000)
        self.assertIn(b"200", status)
        self.assertEqual([len(body) for body in servlet.bodies], [1000])

    def test_invalid_servlet_limit(self) -> None:
        """
        An unusable value given by a servlet removes the limit, like it does
        for the HTTP service
        """
        servlet = EchoServlet()
        self.context.register_service(
            http.HTTP_SERVLET,
            servlet,
            {http.HTTP_SERVLET_PATH: "/invalid", http.HTTP_MAX_BODY_SIZE: "not a size"},
        )

        status, _ = self.post("/invalid", 1000)
        self.assertIn(b"200", status)
        self.assertEqual([len(body) for body in servlet.bodies], [1000])


@unittest.skipIf(importlib.util.find_spec("aiohttp") is None, "aiohttp library not available")
class AsyncPerServletLimitsTest(PerServletLimitsTest):
    """
    Same tests, against the asynchronous HTTP service
    """

    http_bundle = "pelix.http.basic_async"
    http_factory = http.FACTORY_HTTP_ASYNC

    def test_async_servlet_limit(self) -> None:
        """
        An asynchronous servlet reads the body itself, without going through
        aiohttp: read_data() must apply the limit on its own
        """
        servlet = AsyncEchoServlet()
        self.context.register_service(
            http.HTTP_SERVLET_ASYNC, servlet, {http.HTTP_SERVLET_ASYNC_PATH: "/async"}
        )

        # Over the limit of the service
        status, _ = self.post("/async", 1000)
        self.assertIn(b"413", status)
        self.assertListEqual(servlet.bodies, [])

        # Under the limit of the service
        status, _ = self.post("/async", 50)
        self.assertIn(b"200", status)
        self.assertEqual([len(body) for body in servlet.bodies], [50])

    def test_async_servlet_chunked_limit(self) -> None:
        """
        The limit must also be applied to a chunked body, which doesn't declare
        its size
        """
        servlet = AsyncEchoServlet()
        self.context.register_service(
            http.HTTP_SERVLET_ASYNC, servlet, {http.HTTP_SERVLET_ASYNC_PATH: "/chunked"}
        )

        # Send 1000 bytes in chunks of 100, without any content length
        chunk = b"x" * 100
        raw = b"POST /chunked HTTP/1.1\r\nHost: localhost\r\nTransfer-Encoding: chunked\r\n\r\n"
        raw += (b"64\r\n" + chunk + b"\r\n") * 10
        raw += b"0\r\n\r\n"

        with socket.create_connection((DEFAULT_HOST, self.port), timeout=10.0) as sock:
            sock.sendall(raw)
            answer = sock.recv(4096)

        self.assertIn(b"413", answer.splitlines()[0])
        self.assertListEqual(servlet.bodies, [])

    def test_async_servlet_raises_the_limit(self) -> None:
        """
        An asynchronous servlet can also override the limit of the service
        """
        servlet = AsyncEchoServlet()
        self.context.register_service(
            http.HTTP_SERVLET_ASYNC,
            servlet,
            {http.HTTP_SERVLET_ASYNC_PATH: "/async-large", http.HTTP_MAX_BODY_SIZE: 4096},
        )

        status, _ = self.post("/async-large", 1000)
        self.assertIn(b"200", status)
        self.assertEqual([len(body) for body in servlet.bodies], [1000])


class RequestThreadsTest(unittest.TestCase):
    """
    Tests the lifecycle of the threads handling the requests
    """

    framework: Framework
    ipopo: IPopoService

    def setUp(self) -> None:
        """
        Prepares a framework with the basic HTTP service
        """
        self.framework = create_framework([])
        self.framework.start()
        self.ipopo = install_ipopo(self.framework)

        context = self.framework.get_bundle_context()
        context.install_bundle("pelix.http.basic").start()

        self.service = cast(
            http.HTTPService,
            self.ipopo.instantiate(
                http.FACTORY_HTTP_BASIC,
                "test-http-threads",
                {http.HTTP_SERVICE_ADDRESS: DEFAULT_HOST, http.HTTP_SERVICE_PORT: 0},
            ),
        )

    def tearDown(self) -> None:
        """
        Cleans up for the next test
        """
        FrameworkFactory.delete_framework(self.framework)
        self.framework = None  # type: ignore

    def test_threads_are_tracked(self) -> None:
        """
        The server must use the bookkeeping of ThreadingMixIn, else
        server_close() can neither wait for nor account for the requests being
        handled
        """
        port = self.service.get_access()[1]
        server = cast(Any, self.service)._server

        # ThreadingMixIn replaces its class-level "_NoThreads" sentinel, which
        # ignores everything it is given, by a "_Threads" list on first use
        self.assertNotIsInstance(server._threads, list, "The server is not in its initial state")

        with socket.create_connection((DEFAULT_HOST, port), timeout=10.0) as sock:
            sock.sendall(b"GET /unknown HTTP/1.0\r\nHost: localhost\r\n\r\n")
            self.assertTrue(sock.recv(4096), "No answer from the server")

        # The thread of that request must have been registered
        self.assertIsInstance(server._threads, list, "The request threads are not tracked")

    def test_thread_name_and_daemon_flag(self) -> None:
        """
        The thread handling a request must be named after its client and follow
        the daemon_threads flag of the server, both of which are applied by
        ThreadingMixIn.process_request()
        """
        port = self.service.get_access()[1]
        server = cast(Any, self.service)._server

        handling_threads: list[threading.Thread] = []

        class RecorderServlet:
            def do_GET(self, request: Any, response: Any) -> None:
                handling_threads.append(threading.current_thread())
                response.send_content(200, "OK", "text/plain")

        context = self.framework.get_bundle_context()
        context.register_service(http.HTTP_SERVLET, RecorderServlet(), {http.HTTP_SERVLET_PATH: "/recorder"})

        with socket.create_connection((DEFAULT_HOST, port), timeout=10.0) as sock:
            sock.sendall(b"GET /recorder HTTP/1.0\r\nHost: localhost\r\n\r\n")
            self.assertTrue(sock.recv(4096), "No answer from the server")

        self.assertEqual(len(handling_threads), 1, "The servlet has not been called")
        thread = handling_threads[0]

        # The name gives the client, which is the whole point of the override
        self.assertTrue(
            thread.name.startswith(f"HttpService-{port}-Client-"),
            f"Unexpected thread name: {thread.name}",
        )

        # The flag of the server is applied, whatever its value...
        self.assertIs(thread.daemon, server.daemon_threads)

        # ... and its value is the one which lets server_close() wait for the
        # requests being handled
        self.assertFalse(thread.daemon, "The request threads must not be daemons")

    def test_no_thread_left_after_shutdown(self) -> None:
        """
        Killing the HTTP service must not leave a request handling thread alive
        """
        port = self.service.get_access()[1]

        for _ in range(3):
            with socket.create_connection((DEFAULT_HOST, port), timeout=10.0) as sock:
                sock.sendall(b"GET /unknown HTTP/1.0\r\nHost: localhost\r\n\r\n")
                self.assertTrue(sock.recv(4096), "No answer from the server")

        self.ipopo.kill("test-http-threads")

        self.assertListEqual(list_request_threads(), [], "A request thread is still alive")


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
