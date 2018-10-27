#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
XMPP shell: XMPP interface for the Pelix shell

This module depends on the sleekxmpp package: http://sleekxmpp.com/

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
import argparse
import collections
import logging
import sys

try:
    # Python 2
    from StringIO import StringIO
except ImportError:
    # Python 3
    from io import StringIO

# SleekXMPP
import sleekxmpp

# iPOPO decorators
from pelix.ipopo.decorators import (
    ComponentFactory,
    Requires,
    Property,
    Validate,
    Invalidate,
    HiddenProperty,
)
from pelix.ipopo.constants import use_ipopo

# Pelix utilities
import pelix.framework
import pelix.misc.xmpp
import pelix.threadpool
import pelix.utilities

# Shell constants
from pelix.shell.console import (
    make_common_parser,
    handle_common_arguments,
    remove_duplicates,
)
import pelix.shell
import pelix.shell.beans as beans

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Logger
_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


class _XmppOutStream(object):
    """
    File-like XMPP output. For shell IOHandler use only
    """

    def __init__(self, client, target):
        """
        Sets up the stream

        :param client: XMPP client
        :param target: Output target JID
        """
        self._client = client
        self._target = target
        self._buffer = StringIO()

        # Indicate to the I/O handler that we want strings, not bytes
        self.encoding = "utf-8"

    def write(self, data):
        """
        Writes data to a buffer
        """
        self._buffer.write(data)

    def flush(self):
        """
        Sends buffered data to the target
        """
        # Flush buffer
        content = self._buffer.getvalue()
        self._buffer = StringIO()

        if content:
            # Send message
            self._client.send_message(self._target, content, mtype="chat")


class _XmppInStream(object):
    """
    File-like XMPP input. For shell IOHandler use only
    """

    def __init__(self, xmpp_ui, source_jid):
        """
        Sets up the object

        :param xmpp_ui: The IPopoXMPPShell object
        """
        self._ui = xmpp_ui
        self._jid = source_jid

    def readline(self):
        """
        Waits for a line from the XMPP client
        """
        # Wait for content from the user
        return self._ui.read_from(self._jid)


# ------------------------------------------------------------------------------


@ComponentFactory(pelix.shell.FACTORY_XMPP_SHELL)
@Requires("_shell", pelix.shell.SERVICE_SHELL)
@Property("_host", "shell.xmpp.server", "localhost")
@Property("_port", "shell.xmpp.port", 5222)
@Property("_jid", "shell.xmpp.jid")
@HiddenProperty("_password", "shell.xmpp.password")
@Property("_use_tls", "shell.xmpp.tls", "1")
@Property("_use_ssl", "shell.xmpp.ssl", "0")
class IPopoXMPPShell(object):
    """
    The iPOPO XMPP Shell, based on the Pelix Shell
    """

    def __init__(self):
        """
        Sets up the component
        """
        # Injected fields
        self._shell = None
        self._host = None
        self._port = 5222
        self._jid = None
        self._password = None
        self._use_tls = True
        self._use_ssl = False

        # XMPP Bot
        self.__bot = None

        # Shell sessions: JID -> ShellSession
        self.__sessions = {}

        # Waiting for a message from the given JID
        self.__waiting = {}

        # Task queue thread
        self.__pool = pelix.threadpool.ThreadPool(1, logname="XMPPShell")

    @staticmethod
    def __normalize_int(value, default=0):
        """
        Normalizes an integer value
        """
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    @Validate
    def validate(self, _):
        """
        Component validated
        """
        # Normalize values
        self._port = self.__normalize_int(self._port, 5222)
        self._use_tls = bool(self.__normalize_int(self._use_tls, 1))
        self._use_ssl = bool(self.__normalize_int(self._use_ssl, 0))

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
        self.__bot.connect(
            self._host, self._port, False, self._use_tls, self._use_ssl
        )

    @Invalidate
    def invalidate(self, _):
        """
        Component invalidated
        """
        # Stop the thread pool
        self.__pool.stop()

        # Disconnect the bot
        self.__bot.disconnect()
        self.__bot = None

        # Clean up
        self.__sessions.clear()

    @staticmethod
    def __on_error(error):
        """
        A socket error occurred

        :param error: The socket error
        """
        _logger.exception("A socket error occurred: %s", error)

    def __on_start(self, _):
        """
        XMPP session started
        """
        _logger.info(
            "XMPP shell connected with JID: %s", self.__bot.boundjid.full
        )

    def __on_end(self, _):
        """
        XMPP session ended
        """
        _logger.info(
            "XMPP shell disconnected from %s", self.__bot.boundjid.full
        )

    def __on_offline(self, data):
        """
        XMPP client got offline
        :param data: Message stanza
        """
        source_jid = data["from"].full
        try:
            # Unsubscribe to presence events
            self.__bot.sendPresence(pto=source_jid, ptype="unsubscribe")

            # Delete the corresponding session
            del self.__sessions[source_jid]
        except KeyError:
            # Unknown JID
            pass

    def __on_message(self, data):
        """
        Got an XMPP message

        :param data: Message stanza (see SleekXMPP)
        """
        if data["type"] in ("normal", "chat"):
            # Got a message
            body = data["body"].strip()
            if body:
                # Valid content, check the sender
                sender = data["from"].full
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

    def handle_message(self, source_jid, content):
        """
        Handles an XMPP message and reply to the source

        :param source_jid: JID of the message sender
        :param content: Content of the message
        """
        try:
            # Use the existing session
            session = self.__sessions[source_jid]
        except KeyError:
            # Subscribe to presence messages
            self.__bot.sendPresence(pto=source_jid, ptype="subscribe")

            # Create and store the session
            session = self.__sessions[source_jid] = beans.ShellSession(
                beans.IOHandler(
                    _XmppInStream(self, source_jid),
                    _XmppOutStream(self.__bot, source_jid),
                ),
                {"xmpp.jid": source_jid},
            )

        self._shell.execute(content, session)

    def read_from(self, jid):
        """
        Returns the next message read from the given JID

        :param jid: Source JID
        :return: The next content send by this JID
        """
        # Prepare an event
        event = pelix.utilities.EventData()
        self.__waiting.setdefault(jid, collections.deque()).append(event)

        # Wait for the event to be set...
        event.wait()

        # Return the message content
        return event.data


# ------------------------------------------------------------------------------


def main(argv=None):
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
            _logger.error(
                "getpass() unavailable: give a password in command line"
            )
        else:
            try:
                password = getpass.getpass()
            except getpass.GetPassWarning:
                pass

    # Get the server from the JID, if necessary
    server = args.server
    if not server:
        server = sleekxmpp.JID(args.jid).domain

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
    framework = pelix.framework.create_framework(
        remove_duplicates(bundles), init.properties
    )
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
    except KeyboardInterrupt:
        framework.stop()


if __name__ == "__main__":
    # Run the entry point
    sys.exit(main() or 0)
