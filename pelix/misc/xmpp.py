#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
XMPP bot classes: Small classes inheriting from SleekXMPP to ease the
development of bots in Pelix

This module depends on the sleekxmpp package: http://sleekxmpp.com/

:author: Thomas Calmant
:copyright: Copyright 2023, Thomas Calmant
:license: Apache License 2.0
:version: 1.0.2

..

    Copyright 2023 Thomas Calmant

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

import asyncio
import inspect
import logging
import os
import selectors
import ssl
import threading
from asyncio import Future
from typing import Any, AsyncGenerator, Dict, Optional, Union

# XMPP, based on slixmpp, replacing sleekxmpp
from slixmpp.basexmpp import BaseXMPP
from slixmpp.clientxmpp import ClientXMPP
from slixmpp.jid import JID
from slixmpp.xmlstream import JID

from pelix.utilities import EventData

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


class BasicBot(ClientXMPP):
    """
    Basic bot: connects to a server with the given credentials
    """

    def __init__(
        self, jid: Union[str, JID], password: str, initial_priority: int = 0, ssl_verify: bool = False
    ) -> None:
        """
        :param jid: Full Jabber ID of the bot
        :param password: Account password
        :param initial_priority: Initial presence priority
        :param ssl_verify: If true, verify the server certificate
        """
        # ID of the loop thread
        self.__thread_id: Optional[int] = None

        # Set up the client
        ClientXMPP.__init__(self, jid, password)

        # End of loop marker
        self.__loop_stop: Optional[asyncio.Future[bool]] = None

        # Store parameters
        self._initial_priority: int = initial_priority

        # SSL verification
        self.__ssl_verify: bool = ssl_verify

        # Connection event
        self._connected_event: EventData[Any] = EventData()

        # Register the plug-ins: Form and Ping
        self.register_plugin("xep_0004")
        self.register_plugin("xep_0199")

        # Register to session start event
        self.add_event_handler("session_start", self.on_session_start)

    def _run_loop(self) -> None:
        """
        Runs the XMPP asyncio loop in a thread
        """
        try:
            asyncio.set_event_loop(self.loop)
            self.__loop_stop = self.loop.create_future()
            try:
                while self.__loop_stop is not None and not self.__loop_stop.done():
                    try:
                        self.loop.run_until_complete(asyncio.wait_for(asyncio.shield(self.__loop_stop), 60))
                    except asyncio.TimeoutError:
                        pass

                _logger.debug("XMPP loop stopped - %s", self.boundjid)
                pending = asyncio.all_tasks(self.loop)
                for p in pending:
                    # Cancel all pending tasks
                    p.cancel()

                if pending:
                    # Consume cancelled tasks
                    self.loop.run_until_complete(asyncio.wait(pending))
            except Exception:
                _logger.exception("Error in XMPP loop")
            finally:
                self.loop.close()
                self.__loop_stop = None
        except Exception:
            _logger.exception("Error in XMPP loop")

    def __del__(self) -> None:
        """
        Ensure we are disconnected when the bot is deleted
        """
        if self.__loop_stop is not None:
            self.disconnect()

    def get_ssl_context(self) -> ssl.SSLContext:
        """
        Returns a SSL context that doesn't check the host name nor the certificate
        """
        ctx = super().get_ssl_context()
        if not self.__ssl_verify:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        else:
            ctx.check_hostname = True
            ctx.verify_mode = ssl.CERT_REQUIRED
        return ctx

    def connect(
        self,
        host: str,
        port: int = 5222,
        use_tls: bool = True,
        use_ssl: bool = False,
    ) -> bool:
        # pylint: disable=W0221
        """
        Connects to the server.

        By default, uses an un-encrypted connection, as it won't connect to an
        OpenFire server otherwise

        :param host: Server host name
        :param port: Server port (default: 5222)
        :param use_tls: Use STARTTLS
        :param use_ssl: Server connection is encrypted
        :return: True if connection succeeded
        """
        if not self._expected_server_name:
            # We seem to connect the server anonymously, so SleekXMPP
            # couldn't find the server host name from the JID
            # => give it the given server host name as the expected one
            self._expected_server_name = host

        # Register to connection events
        self.add_event_handler("connecting", lambda _: _logger.debug("Connecting to [%s]:%s", host, port))
        self.add_event_handler("connection_failed", self.__on_connect_error)
        self.add_event_handler("connected", self.__on_connect)
        self.add_event_handler("disconnected", self.__on_disconnect)
        self.add_event_handler("session_start", self.on_session_start)
        self.add_event_handler("stream_error", self.on_stream_error)
        self.add_event_handler("ssl_invalid_chain", self.on_ssl_error)
        self.add_event_handler("message_error", self.on_message_error)

        if os.name == "nt":
            # On Windows, use the SelectSelector
            class EventLoopPolicy(asyncio.DefaultEventLoopPolicy):
                """
                Event loop policy that uses a SelectSelector on Windows
                """

                def new_event_loop(self) -> asyncio.AbstractEventLoop:
                    """
                    Creates a new event loop
                    """
                    selector = selectors.SelectSelector()
                    return asyncio.SelectorEventLoop(selector)

            _logger.debug("Using a SelectSelector on Windows")
            asyncio.set_event_loop_policy(EventLoopPolicy())

        self.loop = asyncio.new_event_loop()
        self.loop.set_debug(True)
        thread = threading.Thread(target=self._run_loop, name=f"XMPP loop {self.boundjid.bare}")
        thread.start()
        self.__thread_id = thread.ident

        self._connected_event.clear()
        self.loop.call_soon_threadsafe(super().connect, (host, port), use_ssl, use_tls)
        # Wait for the connection to be established
        if not self._connected_event.wait(5):
            raise IOError("XMPP connection timeout")

        return True

    def __getattribute__(self, __name: str) -> Any:
        """
        Wraps all non-coroutine methods to ensure they are called in the loop thread
        """
        attr = super().__getattribute__(__name)

        if (
            (inspect.ismethod(attr) or inspect.isfunction(attr))
            and not asyncio.iscoroutine(attr)
            and not asyncio.iscoroutinefunction(attr)
            and self.__thread_id is not None
            and threading.current_thread().ident != self.__thread_id
            and not self.loop.is_closed()
        ):
            # Ensure that the method is called in the loop thread
            def wrapped(*args: Any, **kwds: Any) -> Any:
                """
                Wraps the method call
                """
                event = EventData[Any]()

                def underwrapped() -> None:
                    """
                    Effectively calls the method and stores its result in an event
                    """
                    try:
                        event.set(attr(*args, **kwds))
                    except Exception as ex:
                        _logger.exception("Calling %s in the XMPP loop failed", __name)
                        event.raise_exception(ex)

                self.loop.call_soon_threadsafe(underwrapped)
                return event.wait()

            return wrapped
        return attr

    def disconnect(
        self, wait: Union[float, int] = 2, reason: Optional[str] = None, ignore_send_queue: bool = False
    ) -> Future[Any]:
        """
        Calls the parent disconnect method and stops the event loop
        """

        def end_of_loop(future: Future[Any]) -> None:
            """
            Called when the disconnection is done, stops the loop
            """
            if self.__loop_stop is not None:
                self.__loop_stop.set_result(True)

            self.__thread = None
            self.__thread_id = None

        fut = super().disconnect(wait, reason, ignore_send_queue)
        fut.add_done_callback(end_of_loop)
        return fut

    def __on_connect(self, data: Dict[Any, Any]) -> None:
        """
        XMPP client connected: unblock the connect() method
        """
        _logger.debug("XMPP client connected")
        self._connected_event.set()

    def __on_connect_error(self, data: Dict[Any, Any]) -> None:
        """
        Connection error: raise exception in connect()
        """
        _logger.error("Connect error: %s", data)
        self._connected_event.raise_exception(IOError("XMPP connection error"))

    def __on_disconnect(self, data: Any) -> None:
        """
        Disconnection event: stop the loop
        """
        _logger.debug("XMPP client disconnected")
        self._connected_event.clear()

    async def on_session_start(self, data: Any) -> None:
        # pylint: disable=W0613
        """
        XMPP session started
        """
        _logger.debug("XMPP session started")
        # Send initial presence
        self.send_presence(ppriority=self._initial_priority)
        # Request roster
        await self.get_roster()

    def on_stream_error(self, data: Any) -> None:
        """
        XMPP Stream error: raise exception in connect()
        """
        _logger.error("XMPP Stream error: %s", data)
        self._connected_event.raise_exception(IOError("XMPP Stream error"))

    def on_message_error(self, data: Any) -> None:
        """
        Log message errors
        """
        _logger.error("XMPP Message error: %s", data)

    def on_ssl_error(self, ex: ssl.SSLError) -> None:
        """
        SSL error: raise exception in connect()
        """
        _logger.error("XMPP SSL error: %s", ex)
        self._connected_event.raise_exception(ex)


# ------------------------------------------------------------------------------


class InviteMixIn(BaseXMPP):
    """
    A bot that automatically accepts invites from other participants
    """

    def __init__(self, nick: str) -> None:
        # pylint: disable=W0231
        """
        Sets up the Mix-in

        :param nick: Nickname to use in rooms
        """
        # Store nick
        self._nick: str = nick

        # Register the Multi-User Chat plug-in
        self.register_plugin("xep_0045")

        # Activate the plug-in
        self.invite_start()

    def invite_start(self) -> None:
        """
        Activates the mix-in.
        """
        self.add_event_handler("groupchat_invite", self.on_invite)

    def invite_stop(self) -> None:
        """
        Deactivates the mix-in
        """
        self.del_event_handler("groupchat_invite", self.on_invite)

    def on_invite(self, data: Dict[str, Any]) -> None:
        """
        Multi-User Chat invite
        """
        if not self._nick:
            self._nick = self.boundjid.node

        # Join the room
        self.plugin["xep_0045"].joinMUC(data["from"], self._nick)


# ------------------------------------------------------------------------------


class ServiceDiscoveryMixin(BaseXMPP):
    """
    Adds utility methods to a bot to look for services
    """

    def __init__(self) -> None:
        # pylint: disable=W0231
        """
        Sets up the Mix-in
        """
        # Register the ServiceDiscovery plug-in
        self.register_plugin("xep_0030")

    async def iter_services(self, feature: Optional[str] = None) -> AsyncGenerator[JID, None]:
        """
        Iterates over the root-level services on the server which provides the
        requested feature

        :param feature: Feature that the service must provide (optional)
        :return: A generator of services JID
        """
        # Get the list of root services
        items = await self.plugin["xep_0030"].get_items(
            jid=self.boundjid,
            ifrom=self.boundjid,
            block=True,
            timeout=10,
        )

        for item in items["disco_items"]["items"]:
            # Each item is a 3-tuple. The service JID is the first entry
            if not feature:
                # No filter
                yield item[0]
            else:
                # Get service details
                info = await self.plugin["xep_0030"].get_info(
                    jid=item[0],
                    ifrom=self.boundjid.full,
                    block=True,
                    timeout=10,
                )
                if feature in info["disco_info"]["features"]:
                    # The service provides the required feature
                    yield item[0]
