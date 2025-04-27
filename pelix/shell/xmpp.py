#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
XMPP shell: XMPP interface for the Pelix shell

This module depends on the sleekxmpp package: http://sleekxmpp.com/

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

import argparse
import collections
import logging
import sys
from io import StringIO
from typing import IO, Any, Deque, Dict, List, Optional, cast

from slixmpp.jid import JID

import pelix.framework
import pelix.misc.xmpp
import pelix.shell
import pelix.shell.beans as beans
from pelix.ipopo.constants import use_ipopo
from pelix.ipopo.decorators import ComponentFactory, HiddenProperty, Invalidate, Property, Requires, Validate
from pelix.shell.console import handle_common_arguments, make_common_parser
from pelix.threadpool import ThreadPool
from pelix.utilities import EventData, remove_duplicates

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Logger
_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


class _XmppOutStream(IO[str]):
    """
    File-like XMPP output. For shell IOHandler use only
    """

    def __init__(self, client: pelix.misc.xmpp.BasicBot, target: JID) -> None:
        """
        Sets up the stream

        :param client: XMPP client
        :param target: Output target JID
        """
        self._client: pelix.misc.xmpp.BasicBot = client
        self._target: JID = target
        self._buffer: StringIO = StringIO()

        # Indicate to the I/O handler that we want strings, not bytes
        self.encoding: str = "utf-8"

    @property
    def mode(self) -> str:
        """
        Indicate we're not in binary mode
        """
        return "w"

    def write(self, data: str) -> None:
        """
        Writes data to a buffer
        """
        self._buffer.write(data)

    def flush(self) -> None:
        """
        Sends buffered data to the target
        """
        # Flush buffer
        content = self._buffer.getvalue()
        self._buffer = StringIO()

        if content:
            # Send message
            try:
                self._client.send_message(mto=self._target, mbody=content, mtype="chat")
            except Exception as ex:
                _logger.exception("Error while sending message: %s", ex)
                raise ex


class _XmppInStream(IO[str]):
    """
    File-like XMPP input. For shell IOHandler use only
    """

    def __init__(self, xmpp_ui: "IPopoXMPPShell", source_jid: JID) -> None:
        """
        Sets up the object

        :param xmpp_ui: The IPopoXMPPShell object
        :param source_jid: Client JID
        """
        self._ui = xmpp_ui
        self._jid = source_jid

    @property
    def mode(self) -> str:
        """
        Indicate we're not in binary mode
        """
        return "r"

    def readline(self) -> Optional[str]:
        """
        Waits for a line from the XMPP client
        """
        # Wait for content from the user
        return self._ui.read_from(self._jid)


# ------------------------------------------------------------------------------


@ComponentFactory(pelix.shell.FACTORY_XMPP_SHELL)
@Requires("_shell", pelix.shell.ShellService)
@Property("_host", "shell.xmpp.server", "localhost")
@Property("_port", "shell.xmpp.port", 5222)
@Property("_jid", "shell.xmpp.jid")
@HiddenProperty("_password", "shell.xmpp.password")
@Property("_use_tls", "shell.xmpp.tls", "1")
@Property("_use_ssl", "shell.xmpp.ssl", "0")
class IPopoXMPPShell:
    """
    The iPOPO XMPP Shell, based on the Pelix Shell
    """

    _shell: pelix.shell.ShellService

    def __init__(self) -> None:
        """
        Sets up the component
        """
        # Injected properties
        self._host: str = "localhost"
        self._port: int = 5222
        self._jid: Optional[str] = None
        self._password: Optional[str] = None
        self._use_tls: bool = True
        self._use_ssl: bool = False

        # XMPP Bot
        self.__bot: Optional[pelix.misc.xmpp.BasicBot] = None

        # Shell sessions: JID -> ShellSession
        self.__sessions: Dict[JID, beans.ShellSession] = {}

        # Waiting for a message from the given JID
        self.__waiting: Dict[JID, Deque[EventData[str]]] = {}

        # Task queue thread
        self.__pool: ThreadPool = ThreadPool(1, logname="XMPPShell")

    @staticmethod
    def __normalize_int(value: Any, default: int = 0) -> int:
        """
        Normalizes an integer value
        """
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    @Validate
    def validate(self, _: pelix.framework.BundleContext) -> None:
        """
        Component validated
        """
        # Normalize values
        self._port = self.__normalize_int(self._port, 5222)
        self._use_tls = bool(self.__normalize_int(self._use_tls, 1))
        self._use_ssl = bool(self.__normalize_int(self._use_ssl, 0))

        # Check other values
        if not self._host:
            _logger.error("No XMPP server host given. Abandon.")
            raise ValueError("No XMPP server host given")

        if not self._jid or not self._password:
            _logger.error("No JID or password given. Abandon.")
            raise ValueError("No JID or password given")

        # Start the thread pool
        self.__pool.start()

        _logger.info(
            """XMPP shell:
- JID: %s
- host: %s
- port: %s""",
            self._jid,
            self._host,
            self._port,
        )

        # Create the bot. Negative priority avoids listening to human messages
        self.__bot = pelix.misc.xmpp.BasicBot(self._jid, self._password)
        self.__bot.auto_authorize = True

        # Register to events
        self.__bot.add_event_handler("message", self.__on_message)
        self.__bot.add_event_handler("session_start", self.__on_start)
        self.__bot.add_event_handler("session_end", self.__on_end)
        self.__bot.add_event_handler("socket_error", self.__on_error)
        self.__bot.add_event_handler("got_offline", self.__on_offline)

        # Connect to the server
        self.__bot.connect(self._host, self._port, self._use_tls, self._use_ssl)

    @Invalidate
    def invalidate(self, _: pelix.framework.BundleContext) -> None:
        """
        Component invalidated
        """
        # Stop the thread pool
        self.__pool.stop()

        if self.__bot is not None:
            # Disconnect the bot
            self.__bot.disconnect()
            self.__bot = None

        # Clean up
        self.__sessions.clear()

    @staticmethod
    def __on_error(error: str) -> None:
        """
        A socket error occurred

        :param error: The socket error
        """
        _logger.exception("A socket error occurred: %s", error)

    def __on_start(self, _: Any) -> None:
        """
        XMPP session started
        """
        if self.__bot is None:
            _logger.error("No XMPP bot on session start")
            return

        _logger.info("XMPP shell connected with JID: %s", self.__bot.boundjid.full)

    def __on_end(self, _: Any) -> None:
        """
        XMPP session ended
        """
        if self.__bot is None:
            _logger.error("No XMPP bot on session end")
            return

        _logger.info("XMPP shell disconnected from %s", self.__bot.boundjid.full)

    def __on_offline(self, data: Dict[str, Any]) -> None:
        """
        XMPP client got offline
        :param data: Message stanza
        """
        source_jid = data["from"]

        try:
            # Delete the corresponding session
            del self.__sessions[source_jid]
        except KeyError:
            # Ignore unknown JID
            pass
        else:
            if self.__bot is not None:
                # Unsubscribe to presence events
                self.__bot.send_presence(pto=source_jid, ptype="unsubscribe")
            else:
                _logger.debug("No XMPP bot: cannot unsubscribe %s", source_jid)

    def __on_message(self, data: Dict[str, Any]) -> None:
        """
        Got an XMPP message

        :param data: Message stanza (see SleekXMPP)
        """
        if self.__bot is None:
            _logger.error("No XMPP bot: cannot handle message")
            return

        if data["type"] in ("normal", "chat"):
            # Got a message
            body = cast(str, data["body"]).strip()
            if body:
                # Valid content, check the sender
                sender = cast(JID, data["from"])
                try:
                    # Are we listening to this JID ?
                    event = self.__waiting[sender].popleft()
                except (KeyError, IndexError):
                    # Not waiting for a message from this JID,
                    # treat the message in a the task thread
                    self.__pool.enqueue(self.handle_message, sender, body)
                else:
                    # Set the event, with the content of the message as data
                    event.set(body)

    def handle_message(self, source_jid: JID, content: str) -> None:
        """
        Handles an XMPP message and reply to the source

        :param source_jid: JID of the message sender
        :param content: Content of the message
        """
        try:
            # Use the existing session
            session = self.__sessions[source_jid]
        except KeyError:
            if self.__bot is None:
                _logger.error("No XMPP bot: cannot handle message")
                return

            # Subscribe to presence messages
            self.__bot.send_presence(pto=source_jid, ptype="subscribe")

            # Create and store the session
            session = self.__sessions[source_jid] = beans.ShellSession(
                beans.IOHandler(
                    _XmppInStream(self, source_jid),
                    _XmppOutStream(self.__bot, source_jid),
                ),
                {"xmpp.jid": source_jid},
            )

        self._shell.execute(content, session)

    def read_from(self, jid: JID) -> Optional[str]:
        """
        Returns the next message read from the given JID

        :param jid: Source JID
        :return: The next content send by this JID
        """
        # Prepare an event
        event = EventData[str]()
        self.__waiting.setdefault(jid, collections.deque()).append(event)

        # Wait for the event to be set...
        event.wait()

        # Return the message content
        return event.data


# ------------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    """
    Entry point

    :param argv: Script arguments (None for sys.argv)
    :return: An exit code or None
    """
    # Prepare arguments
    parser = argparse.ArgumentParser(
        prog="pelix.shell.xmpp",
        parents=[make_common_parser()],
        description="Pelix XMPP Shell",
    )

    group = parser.add_argument_group("XMPP options")
    group.add_argument("-j", "--jid", dest="jid", help="Jabber ID")
    group.add_argument("--password", dest="password", help="JID password")
    group.add_argument("-s", "--server", dest="server", help="XMPP server host")
    group.add_argument(
        "-p",
        "--port",
        dest="port",
        type=int,
        default=5222,
        help="XMPP server port",
    )
    group.add_argument(
        "--tls",
        dest="use_tls",
        action="store_true",
        help="Use a STARTTLS connection",
    )
    group.add_argument(
        "--ssl",
        dest="use_ssl",
        action="store_true",
        help="Use an SSL connection",
    )

    # Parse them
    args = parser.parse_args(argv)

    # Handle common arguments
    init = handle_common_arguments(args)

    # Quiet down the SleekXMPP logger
    if not args.verbose:
        logging.getLogger("sleekxmpp").setLevel(logging.WARNING)

    if not args.server and not args.jid:
        _logger.error("No JID nor server given. Abandon.")
        sys.exit(1)

    # Get the password if necessary
    password = args.password
    if args.jid and args.password is None:
        try:
            import getpass
        except ImportError:
            _logger.error("getpass() unavailable: give a password in command line")
        else:
            try:
                password = getpass.getpass()
            except getpass.GetPassWarning:
                pass

    # Get the server from the JID, if necessary
    server = args.server
    if not server:
        server = JID(args.jid).domain

    # Set the initial bundles
    bundles = [
        "pelix.ipopo.core",
        "pelix.shell.core",
        "pelix.shell.ipopo",
        "pelix.shell.console",
        "pelix.shell.xmpp",
    ]
    bundles.extend(init.bundles)

    # Use the utility method to create, run and delete the framework
    framework = pelix.framework.create_framework(remove_duplicates(bundles), init.properties)
    framework.start()

    # Instantiate a Remote Shell
    with use_ipopo(framework.get_bundle_context()) as ipopo:
        ipopo.instantiate(
            pelix.shell.FACTORY_XMPP_SHELL,
            "xmpp-shell",
            {
                "shell.xmpp.server": server,
                "shell.xmpp.port": args.port,
                "shell.xmpp.jid": args.jid,
                "shell.xmpp.password": password,
                "shell.xmpp.tls": args.use_tls,
                "shell.xmpp.ssl": args.use_ssl,
            },
        )

    # Instantiate configured components
    init.instantiate_components(framework.get_bundle_context())

    try:
        framework.wait_for_stop()
        return 0
    except KeyboardInterrupt:
        framework.stop()
        return 127


if __name__ == "__main__":
    # Run the entry point
    sys.exit(main())
