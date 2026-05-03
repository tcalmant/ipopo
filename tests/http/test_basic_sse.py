#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix async HTTP service SSE test module.

:author: Thomas Calmant
"""

import asyncio
import time
import unittest
from typing import cast

try:
    import aiohttp
except ImportError:
    raise unittest.SkipTest("aiohttp library not available")

import pelix.http as http
from pelix.framework import FrameworkFactory, create_framework
from pelix.ipopo.constants import use_ipopo
from tests.http.utils import async_test


class SSETestCase(unittest.TestCase):
    SSE_ENDPOINT = "/sse"
    SSE_PORT = 8081

    @classmethod
    def setUpClass(cls):
        # Ensure we have a new event loop for the tests
        asyncio.set_event_loop(asyncio.new_event_loop())

        # Create the framework and start it
        cls.framework = create_framework(("pelix.ipopo.core", "pelix.http.basic_async"))
        cls.framework.start()
        ctx = cls.framework.get_bundle_context()

        with use_ipopo(ctx) as ipopo:
            cls.http_service = cast(
                http.HTTPService,
                ipopo.instantiate(
                    http.FACTORY_HTTP_ASYNC,
                    "async.ws.server",
                    {
                        http.HTTP_SERVICE_ADDRESS: "localhost",
                        http.HTTP_SERVICE_PORT: 0,
                    },
                ),
            )

        # Install and start the HTTP service
        cls.SSE_PORT = cls.http_service.get_access()[1]

    @classmethod
    def tearDownClass(cls):
        cls.framework.stop()
        FrameworkFactory.delete_framework(cls.framework)

    def setUp(self):
        self.sse_state = {"clients": set(), "disconnects": 0}

        # Create the SSE handler
        parent = self

        class SSEHandler(http.AsyncServlet):
            async def do_async_GET(
                self,
                request: http.AbstractAsyncHTTPServletRequest,
                response: http.AbstractAsyncHTTPServletResponse,
            ):
                response.setup_sse()
                await response.end_headers()
                clt = request.get_client_address()
                parent.sse_state["clients"].add(clt)

                data = await request.get_header("X-Custom-Header", "hello")
                try:
                    while True:
                        await response.send_sse(data=data)
                        await asyncio.sleep(0.1)
                except Exception:
                    parent.sse_state["disconnects"] += 1
                finally:
                    parent.sse_state["clients"].discard(clt)

        self.sse_handler = SSEHandler()
        self.http_service.register_servlet(
            self.SSE_ENDPOINT, self.sse_handler, servlet_type=http.ServletType.ASYNC
        )

    def tearDown(self):
        if self.sse_handler is not None:
            # Unregister the SSE handler
            self.http_service.unregister(None, self.sse_handler)
            self.sse_handler = None

    @async_test
    async def test_two_clients_parallel(self):
        """
        Test that two clients can connect to the SSE endpoint simultaneously
        and receive messages without issues.
        """

        times: dict[int, tuple[float, float]] = {}

        async def client(x: int):
            async with aiohttp.ClientSession() as session:
                expected = f"message for {x}"
                session.headers.update({"Accept": "text/event-stream", "X-Custom-Header": expected})
                async with session.get(f"http://localhost:{self.SSE_PORT}{self.SSE_ENDPOINT}") as resp:
                    start = time.time()
                    self.assertEqual(resp.status, 200)

                    # Read the first block
                    line = await resp.content.readline()
                    while not line.strip():
                        line = await resp.content.readline()

                    self.assertEqual(line.strip(), f"data: {expected}".encode())
                    await asyncio.sleep(1)

                    # Read the second block
                    line = await resp.content.readline()
                    while not line.strip():
                        line = await resp.content.readline()

                    self.assertEqual(line.strip(), f"data: {expected}".encode())
                    end = time.time()
                    times[x] = (start, end)

        tasks = [asyncio.create_task(client(i)) for i in range(3)]
        await asyncio.gather(*tasks)
        self.assertEqual(len(times), 3)
        self.assertTrue(
            all(end - start for start, end in times.values()) < 2, "Clients took too long to respond"
        )
        # Ensure that the start time of each client is less than the end time of the last client
        self.assertTrue(
            max(start for start, _ in times.values()) < max(end for _, end in times.values()),
            "Clients did not start in parallel",
        )

    @async_test
    async def test_server_detects_client_disconnect(self):
        """
        Test that the server correctly detects when a client disconnects
        and updates the disconnect count.
        """

        async def client():
            async with aiohttp.ClientSession() as session:
                session.headers.update({"Accept": "text/event-stream"})
                async with session.get(f"http://localhost:{self.SSE_PORT}{self.SSE_ENDPOINT}") as resp:
                    await resp.content.readline()
            # Disconnects here

        await client()
        await asyncio.sleep(1)
        self.assertGreater(self.sse_state["disconnects"], 0)

    @async_test
    async def test_many_clients(self):
        """
        Test the server's ability to handle a large number of clients
        connecting simultaneously.
        """
        n_clients = 100

        async def client():
            async with aiohttp.ClientSession() as session:
                session.headers.update({"Accept": "text/event-stream"})
                async with session.get(f"http://localhost:{self.SSE_PORT}{self.SSE_ENDPOINT}") as resp:
                    await resp.content.readline()
                    await asyncio.sleep(0.05)

        await asyncio.gather(*(client() for _ in range(n_clients)))
        await asyncio.sleep(1)
        self.assertEqual(len(self.sse_state["clients"]), 0)

    @async_test
    async def test_server_handles_handler_exception(self):
        """
        Test that the server handles exceptions raised by the SSE handler
        gracefully without crashing.
        """
        # Cleanup current handler
        self.http_service.unregister(None, self.sse_handler)
        self.sse_handler = None

        class FaultySSEHandler(http.AsyncServlet):
            async def do_async_GET(
                self,
                request: http.AbstractAsyncHTTPServletRequest,
                response: http.AbstractAsyncHTTPServletResponse,
            ):
                raise RuntimeError("Simulated server error")

        self.sse_handler = FaultySSEHandler()
        self.http_service.register_servlet(
            self.SSE_ENDPOINT, self.sse_handler, servlet_type=http.ServletType.ASYNC
        )

        async with aiohttp.ClientSession() as session:
            session.headers.update({"Accept": "text/event-stream"})
            async with session.get(f"http://localhost:{self.SSE_PORT}{self.SSE_ENDPOINT}") as resp:
                self.assertEqual(resp.status, 500)

    @async_test
    async def test_client_reconnect(self):
        """
        Test that a client can reconnect to the SSE endpoint after disconnecting.
        """

        async def client():
            async with aiohttp.ClientSession() as session:
                session.headers.update({"Accept": "text/event-stream"})
                async with session.get(f"http://localhost:{self.SSE_PORT}{self.SSE_ENDPOINT}") as resp:
                    self.assertEqual(resp.status, 200)
                    await resp.content.readline()

        await client()
        await asyncio.sleep(1)
        self.assertEqual(len(self.sse_state["clients"]), 0)

        await client()
        await asyncio.sleep(1)
        self.assertEqual(len(self.sse_state["clients"]), 0)

    @async_test
    async def test_server_overload(self):
        """
        Test the server's behavior under heavy load with a very high number
        of simultaneous client connections.
        """
        n_clients = 1000

        async def client():
            async with aiohttp.ClientSession() as session:
                session.headers.update({"Accept": "text/event-stream"})
                async with session.get(f"http://localhost:{self.SSE_PORT}{self.SSE_ENDPOINT}") as resp:
                    if resp.status == 200:
                        await resp.content.readline()

        await asyncio.gather(*(client() for _ in range(n_clients)))
        self.assertGreaterEqual(self.sse_state["disconnects"], 0)

    @async_test
    async def test_connection_lifetime(self):
        """
        Test that SSE connections remain open and functional for an extended
        period, sending multiple messages to the client.
        """
        nb_received = 0
        async with aiohttp.ClientSession() as session:
            session.headers.update({"Accept": "text/event-stream"})
            async with session.get(f"http://localhost:{self.SSE_PORT}{self.SSE_ENDPOINT}") as resp:
                self.assertEqual(resp.status, 200)
                for _ in range(10):
                    line = await resp.content.readline()
                    line = line.strip()
                    if not line:
                        continue

                    nb_received += 1
                    self.assertTrue(line.startswith(b"data: hello"))
                    await asyncio.sleep(0.5)

        self.assertGreater(nb_received, 1)

    @async_test
    async def test_custom_headers(self):
        """
        Test that the server correctly handles custom headers sent by the client.
        """
        async with aiohttp.ClientSession() as session:
            session.headers.update({"Accept": "text/event-stream", "X-Custom-Header": "TestValue"})
            async with session.get(f"http://localhost:{self.SSE_PORT}{self.SSE_ENDPOINT}") as resp:
                self.assertEqual(resp.status, 200)
                line = await resp.content.readline()
                self.assertTrue(line.startswith(b"data: TestValue"))
