#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
XMPP shell: XMPP interface for the Pelix shell

This module depends on the sleekxmpp package: http://sleekxmpp.com/

:author: Thomas Calmant
:copyright: Copyright 2014, isandlaTech
:license: Apache License 2.0
:version: 0.5.7
:status: Beta

..

    Copyright 2014 isandlaTech

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

# Module version
__version_info__ = (0, 5, 7)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory, Requires, Property, \
    Validate, Invalidate

# Shell constants
import pelix.shell

# Pelix utilities
import pelix.misc.xmpp
import pelix.threadpool
import pelix.utilities

# Standard library
import collections
import logging

try:
    # Python 2
    from StringIO import StringIO
except ImportError:
    # Python 3
    from io import StringIO

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
@Property("_password", "shell.xmpp.password")
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

        # Waiting for a message from the given JID
        self.__waiting = {}

        # Task queue thread
        self.__pool = pelix.threadpool.ThreadPool(1, logname="XMPPShell")

    def __normalize_int(self, value, default=0):
        """
        Normalizes an integer value
        """
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    @Validate
    def validate(self, context):
        """
        Component validated
        """
        # Normalize values
        self._port = self.__normalize_int(self._port, 5222)
        self._use_tls = bool(self.__normalize_int(self._use_tls, 1))
        self._use_ssl = bool(self.__normalize_int(self._use_ssl, 0))

        # Start the thread pool
        self.__pool.start()

        _logger.info("""XMPP shell:
- JID: %s
- pass: %s
- host: %s
- port: %s""", self._jid, self._password, self._host, self._port)

        # Create the bot. Negative priority avoids listening to human messages
        self.__bot = pelix.misc.xmpp.BasicBot(self._jid, self._password, -10)

        # Register to events
        self.__bot.add_event_handler("message", self.__on_message)
        self.__bot.add_event_handler("session_start", self.__on_start)
        self.__bot.add_event_handler("session_end", self.__on_end)
        self.__bot.add_event_handler("socket_error", self.__on_error)

        # Connect to the server
        self.__bot.connect(self._host, self._port, False,
                           self._use_tls, self._use_ssl)

    @Invalidate
    def invalidate(self, context):
        """
        Component invalidated
        """
        # Stop the thread pool
        self.__pool.stop()

        # Disconnect the bot
        self.__bot.disconnect()
        self.__bot = None

    def __on_error(self, error):
        """
        A socket error occurred

        :param error: The socket error
        """
        _logger.exception("A socket error occurred: %s", error)

    def __on_start(self, _):
        """
        XMPP session started
        """
        _logger.info("XMPP shell connected with JID: %s",
                     self.__bot.boundjid.full)

    def __on_end(self, _):
        """
        XMPP session ended
        """
        _logger.info("XMPP shell disconnected from %s",
                     self.__bot.boundjid.full)

    def __on_message(self, data):
        """
        Got an XMPP message

        :param data: Message stanza (see SleekXMPP)
        """
        if data['type'] in ('normal', 'chat', 'groupchat'):
            # Got a message
            body = data['body'].strip()
            if body:
                # Valid content, check the sender
                sender = data['from'].full
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
        self._shell.execute(content,
                            _XmppInStream(self, source_jid),
                            _XmppOutStream(self.__bot, source_jid))

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


def main(server, port, jid=None, password=None, use_tls=False, use_ssl=False):
    """
    Starts a framework with a remote shell and starts an interactive console.

    :param server: XMPP server host
    :param port: XMPP server port
    :param jid: Shell JID
    :param password: Shell JID password
    :param use_tls: Use STARTTLS
    :param use_ssl: Use an SSL connection
    """
    from pelix.ipopo.constants import use_ipopo
    import pelix.framework

    # Start a Pelix framework
    framework = pelix.framework.create_framework(('pelix.ipopo.core',
                                                  'pelix.shell.core',
                                                  'pelix.shell.ipopo',
                                                  'pelix.shell.console',
                                                  'pelix.shell.xmpp'))
    framework.start()
    context = framework.get_bundle_context()

    # Instantiate a Remote Shell
    with use_ipopo(context) as ipopo:
        ipopo.instantiate(pelix.shell.FACTORY_XMPP_SHELL, "xmpp-shell",
                          {"shell.xmpp.server": server,
                           "shell.xmpp.port": port,
                           "shell.xmpp.jid": jid,
                           "shell.xmpp.password": password,
                           "shell.xmpp.tls": use_tls,
                           "shell.xmpp.ssl": use_ssl})

    try:
        framework.wait_for_stop()
    except KeyboardInterrupt:
        # Stop server on interruption
        framework.stop()


if __name__ == '__main__':
    # Prepare arguments
    import argparse
    parser = argparse.ArgumentParser(description="Pelix XMPP Shell")
    parser.add_argument("-j", "--jid", dest="jid", help="Jabber ID")
    parser.add_argument("--password", dest="password", help="JID password")
    parser.add_argument("-v", "--verbose", action="store_true", dest="verbose",
                        help="Set loggers at debug level")
    parser.add_argument("-s", "--server", dest="server",
                        help="XMPP server host")
    parser.add_argument("-p", "--port", dest="port", type=int, default=5222,
                        help="XMPP server port")
    parser.add_argument("--tls", dest="use_tls", action="store_true",
                        help="Use a STARTTLS connection")
    parser.add_argument("--ssl", dest="use_ssl", action="store_true",
                        help="Use an SSL connection")

    # Parse them
    args = parser.parse_args()

    # Prepare the logger
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("sleekxmpp").setLevel(logging.WARNING)

    # Get the password if necessary
    password = args.password
    if args.jid and not args.password:
        try:
            import getpass
        except ImportError:
            _logger.error("getpass() unavailable: give a password in "
                          "command line")
        else:
            try:
                password = getpass.getpass()
            except getpass.GetPassWarning:
                pass

    # Get the server from the JID, if necessary
    server = args.server
    if not server and args.jid:
        import sleekxmpp
        server = sleekxmpp.JID(args.jid).domain

    # Run the entry point
    main(server, args.port, args.jid, password, args.use_tls, args.use_ssl)
