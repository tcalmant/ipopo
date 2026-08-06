#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix async HTTP service websockets test module.

:author: Thomas Calmant
"""

import asyncio
import unittest
from typing import cast

try:
    import aiohttp
    from aiohttp import ClientSession, WSMsgType
except ImportError:
    raise unittest.SkipTest("aiohttp library not available")

from pelix import http
from pelix.framework import FrameworkFactory, create_framework
from pelix.ipopo.constants import use_ipopo
from pelix.utilities import EventData
from tests.http.utils import async_test


def wait_for_service(framework, svc_name, timeout=5.0):
    """
    Waits for a service to be available in the framework.
    """
    import time

    end = time.time() + timeout
    while time.time() < end:
        svc_ref = framework.get_bundle_context().get_service_reference(svc_name)
        if svc_ref is not None:
            return svc_ref
        time.sleep(0.1)
    raise RuntimeError(f"Service '{svc_name}' not available after {timeout} seconds")


class WebSocketTestCase(unittest.TestCase):
    http_server: http.HTTPService
    handler: http.WebSocketHandler | None = None
    ws_url: str

    @classmethod
    def setUpClass(cls):
        # Ensure we have a new event loop for the tests
        asyncio.set_event_loop(asyncio.new_event_loop())

        # Create the framework with an HTTP async service and start it
        cls.framework = create_framework(
            (
                "pelix.ipopo.core",
                "pelix.http.basic_async",
            )
        )
        cls.framework.start()
        ctx = cls.framework.get_bundle_context()

        with use_ipopo(ctx) as ipopo:
            cls.http_server = cast(
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

        cls.ws_url = f"ws://localhost:{cls.http_server.get_access()[1]}/ws/test"

    @classmethod
    def tearDownClass(cls):
        cls.framework.stop()
        FrameworkFactory.delete_framework(cls.framework)

    def tearDown(self):
        # Ensure the WebSocket handler is unregistered after each test
        if self.handler is not None:
            self.http_server.unregister(None, servlet=self.handler)
            self.handler = None

    def register_handler(self, handler: http.WebSocketHandler):
        """
        Registers a new WebSocket handler.
        """
        if self.handler is not None:
            self.http_server.unregister(None, servlet=self.handler)

        self.handler = handler
        if not self.http_server.register_servlet(
            "/ws/test", self.handler, servlet_type=http.ServletType.WEBSOCKET
        ):
            raise RuntimeError("Failed to register WebSocket handler")

    @async_test
    async def test_parallel_websocket_clients(self):
        """
        Tests that multiple WebSocket clients can connect and communicate
        with the server simultaneously.
        """
        # Setup server
        messages: list[str] = []

        class WSHandler(http.AbstractWebSocketHandler):
            async def ws_message(self, session: http.WebSocketSession, message: str):
                messages.append(message)
                await session.send_text(f"Echo: {message}")

        self.register_handler(WSHandler())

        # Setup client
        async def client(name, send_msg, received):
            async with ClientSession() as session, session.ws_connect(self.ws_url) as ws:
                await ws.send_str(send_msg)
                msg = await ws.receive(timeout=1)
                if msg.type == WSMsgType.TEXT:
                    received.append((name, msg.data))

        received = []
        await asyncio.gather(
            client("client1", "hello from client1", received),
            client("client2", "hello from client2", received),
        )

        replies = dict(received)
        self.assertEqual(replies["client1"], "Echo: hello from client1")
        self.assertEqual(replies["client2"], "Echo: hello from client2")
        self.assertIn("hello from client1", messages)
        self.assertIn("hello from client2", messages)

    @async_test
    async def test_server_closes_session(self):
        """
        Tests that the server can close a WebSocket session after sending a message.
        The client should receive the message and then the close event.
        """
        # Setup server
        messages: list[str] = []
        handler_closed = EventData()

        # Handler that closes the connection after receiving a message
        class WSHandler(http.AbstractWebSocketHandler):
            async def ws_message(self, session: http.WebSocketSession, message: str):
                messages.append(message)
                await session.send_text("bye")
                await session.close()

            async def ws_close(self, session: http.WebSocketSession, code: int, reason: str) -> None:
                handler_closed.set(code)

        self.register_handler(WSHandler())

        # Setup client
        async with ClientSession() as session, session.ws_connect(self.ws_url) as ws:
            await ws.send_str("close me")
            msg = await ws.receive(timeout=1)
            self.assertEqual(msg.type, WSMsgType.TEXT)
            self.assertEqual(msg.data, "bye")
            msg = await ws.receive(timeout=1)
            self.assertIn(msg.type, (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.CLOSING))

        # on_close should have been called
        self.assertTrue(handler_closed.wait(1), "Handler close event not set")
        self.assertEqual(handler_closed.data, 1000)

    @async_test
    async def test_client_closes_session(self):
        """
        Tests that the client can close a WebSocket session after sending a message.
        The server should receive the message and then the close event.
        """
        # Setup server
        messages: list[str] = []
        handler_closed = EventData[tuple[int, str]]()

        # Handler that closes the connection after receiving a message
        class WSHandler(http.AbstractWebSocketHandler):
            async def ws_message(self, session: http.WebSocketSession, message: str):
                messages.append(message)
                await session.send_text(f"Echo: {message}")
                await session.close()

            async def ws_close(self, session: http.WebSocketSession, code: int, reason: str) -> None:
                handler_closed.set((code, reason))

        self.register_handler(WSHandler())

        # Setup client
        async with ClientSession() as session, session.ws_connect(self.ws_url) as ws:
            await ws.send_str("client will close")
            msg = await ws.receive(timeout=1)
            self.assertEqual(msg.type, WSMsgType.TEXT)
            self.assertEqual(msg.data, "Echo: client will close")
            await ws.close(code=aiohttp.WSCloseCode.SERVICE_RESTART, message=b"Client closing session")

        self.assertTrue(handler_closed.wait(1), "Handler close event not set")
        assert handler_closed.data is not None
        self.assertEqual(handler_closed.data[0], aiohttp.WSCloseCode.SERVICE_RESTART)
        # Message is not available on the server side
        self.assertEqual(handler_closed.data[1], "Session closed")

    @async_test
    async def test_large_message(self):
        """
        Tests the server's ability to handle large messages.
        """
        large_message = "x" * 10_000  # 10 KB message
        messages = []

        class WSHandler(http.AbstractWebSocketHandler):
            async def ws_message(self, session: http.WebSocketSession, message: str):
                messages.append(message)
                await session.send_text("Received")

        self.register_handler(WSHandler())

        async with ClientSession() as session, session.ws_connect(self.ws_url) as ws:
            await ws.send_str(large_message)
            msg = await ws.receive(timeout=2)
            self.assertEqual(msg.type, WSMsgType.TEXT)
            self.assertEqual(msg.data, "Received")

        self.assertIn(large_message, messages)

    @async_test
    async def test_stress_multiple_clients(self):
        """
        Tests the server's ability to handle a large number of simultaneous WebSocket clients.
        """
        messages = []

        class WSHandler(http.AbstractWebSocketHandler):
            async def ws_message(self, session: http.WebSocketSession, message: str):
                messages.append(message)
                await session.send_text(f"Echo: {message}")

        self.register_handler(WSHandler())

        async def client(name, send_msg):
            async with ClientSession() as session, session.ws_connect(self.ws_url) as ws:
                await ws.send_str(send_msg)
                msg = await ws.receive(timeout=2)
                self.assertEqual(msg.type, WSMsgType.TEXT)
                self.assertEqual(msg.data, f"Echo: {send_msg}")

        # Launch 100 clients simultaneously
        await asyncio.gather(*(client(f"client{i}", f"message {i}") for i in range(100)))

        self.assertEqual(len(messages), 100)
        for i in range(100):
            self.assertIn(f"message {i}", messages)
