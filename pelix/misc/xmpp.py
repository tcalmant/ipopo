#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
XMPP bot classes: Small classes inheriting from SliXMPP to ease the
development of bots in Pelix

This module depends on the slixmpp package: https://slixmpp.readthedocs.io/

:author: Thomas Calmant
:copyright: Copyright 2025, Thomas Calmant
:license: Apache License 2.0
:version: 3.1.0

..

    Copyright 2025 Thomas Calmant

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

import asyncio
import logging
import ssl
import threading
from asyncio import AbstractEventLoop, Future
from typing import Any, AsyncGenerator, Dict, Optional, Union, cast

# XMPP, based on slixmpp, replacing sleekxmpp
from slixmpp.basexmpp import BaseXMPP
from slixmpp.clientxmpp import ClientXMPP
from slixmpp.jid import JID
from slixmpp.types import MessageTypes
from slixmpp.xmlstream import JID

from pelix.utilities import EventData

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


class XMPPBotClient(ClientXMPP):
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
        # Set up the client
        ClientXMPP.__init__(self, jid, password)

        # Store parameters
        self._initial_priority: int = initial_priority

        # SSL verification
        self.__ssl_verify: bool = ssl_verify

        # Connection event
        self._connected_event: EventData[bool] = EventData()
        self._disconnected_event: EventData[bool] = EventData()

        # Register the plug-ins: Form and Ping
        self.register_plugin("xep_0004")
        self.register_plugin("xep_0199")

        # Register to session start event
        self.add_event_handler("session_start", self.on_session_start)

    def __del__(self) -> None:
        """
        Ensure we are disconnected when the bot is deleted
        """
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
    ) -> Future[Any]:
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
        # Setup SSL and TLS
        self.enable_plaintext = not use_ssl and not use_tls
        self.enable_starttls = use_tls
        self.enable_direct_tls = use_ssl

        if not self._expected_server_name:
            # We seem to connect the server anonymously, so SliXMPP
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

        _logger.critical(f"Connect to {host}:{port}, jid='{self.boundjid}' - pass='{self.password}'")
        return super().connect(host, port)

    def __on_connect(self, data: Dict[Any, Any]) -> None:
        """
        XMPP client connected: unblock the connect() method
        """
        _logger.debug("XMPP client connected")
        self._disconnected_event.clear()
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
        self._disconnected_event.set()

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
        plugin = self.plugin["xep_0045"]
        if plugin is not None:
            plugin.join_muc(data["from"], self._nick)


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


class BasicBot:
    """
    Basic bot provided by this service
    """

    def __init__(
        self,
        jid: Union[str, JID],
        password: str,
        initial_priority: int = 0,
        ssl_verify: bool = False,
        bot_class: type[XMPPBotClient] = XMPPBotClient,
    ) -> None:
        self.__loop: AbstractEventLoop | None = None
        self.__thread_stop_event: threading.Event = threading.Event()
        init_call_event: EventData[XMPPBotClient] = EventData()
        self.__thread = threading.Thread(
            target=self.__thread_loop,
            args=(init_call_event, bot_class, jid, password, initial_priority, ssl_verify),
            name=f"XMPP client {jid}",
            daemon=True,
        )
        self.__thread.start()

        if init_call_event.wait(30) and init_call_event.data is not None:
            self.__bot: XMPPBotClient = init_call_event.data
        else:
            raise RuntimeError("Failed to create XMPP bot")

    def stop(self) -> None:
        self.__thread_stop_event.set()

        if self.__thread is not None:
            self.__thread.join()
            self.__thread = None

    def __del__(self) -> None:
        self.stop()

    def __thread_loop(
        self,
        event: EventData[XMPPBotClient],
        bot_class: type[XMPPBotClient],
        jid: Union[str, JID],
        password: str,
        initial_priority: int,
        ssl_verify: bool,
    ) -> None:
        """
        Runs the XMPP asyncio loop in a thread
        """
        self.__loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.__loop)

        try:
            bot = bot_class(jid, password, initial_priority, ssl_verify)
            event.set(bot)
        except Exception as e:
            _logger.exception("Error creating XMPP bot")
            event.raise_exception(e)
            return

        try:
            while not self.__thread_stop_event.is_set():
                # Run the loop until the stop event is set
                self.__loop.run_until_complete(asyncio.shield(asyncio.sleep(0.1)))
        except Exception:
            _logger.exception("Error in XMPP loop")
        finally:
            self.__loop.stop()

    @property
    def boundjid(self) -> JID:
        """
        Returns the JID of the bot
        """
        return self.__bot.boundjid

    @property
    def auto_authorize(self) -> bool | None:
        """
        Returns the auto-authorize flag
        """
        return self.__bot.auto_authorize

    @auto_authorize.setter
    def auto_authorize(self, value: bool | None) -> None:
        """
        Sets the auto-authorize flag
        """
        self.__bot.auto_authorize = value

    def connect(
        self,
        host: str,
        port: int = 5222,
        use_tls: bool = True,
        use_ssl: bool = False,
    ) -> bool:
        if self.__loop is None:
            raise RuntimeError("XMPP bot not initialized")

        run_handle = self.__loop.call_soon_threadsafe(self.__bot.connect, host, port, use_tls, use_ssl)
        if not self.__bot._connected_event.wait(5):
            run_handle.cancel()
            return False

        return True

    def add_event_handler(self, event: str, handler: Any) -> None:
        """
        Adds an event handler to the bot
        """
        self.__bot.add_event_handler(event, handler)

    def update_roster(self, jid: Union[str, JID], **kwargs) -> None:
        """
        Updates the roster for the given JID
        """
        if self.__loop is None:
            raise RuntimeError("XMPP bot not initialized")

        def call_update_roster():
            return self.__bot.update_roster(JID(jid), **kwargs)

        self.__loop.call_soon_threadsafe(call_update_roster)

    def send_presence(self, **kwargs) -> None:
        """
        Sends a presence to the server
        """
        if self.__loop is None:
            raise RuntimeError("XMPP bot not initialized")

        def call_send_presence():
            return self.__bot.send_presence(**kwargs)

        self.__loop.call_soon_threadsafe(call_send_presence)

    def send_message(
        self,
        mto: JID | str,
        mbody: str | None = None,
        msubject: str | None = None,
        mtype: str | None = None,
        mhtml: str | None = None,
        mfrom: JID | str | None = None,
        mnick: str | None = None,
    ) -> None:
        """
        Sends a message to the given JID
        """
        if self.__loop is None:
            raise RuntimeError("XMPP bot not initialized")

        self.__loop.call_soon_threadsafe(
            self.__bot.send_message, JID(mto), mbody, msubject, cast(MessageTypes, mtype), mhtml, mfrom, mnick
        )

    def disconnect(self) -> bool:
        """
        Disconnects the bot
        """
        if self.__loop is None:
            raise RuntimeError("XMPP bot not initialized")

        run_handle = self.__loop.call_soon_threadsafe(self.__bot.disconnect)
        if not self.__bot._disconnected_event.wait(5):
            run_handle.cancel()
            return False

        return True
