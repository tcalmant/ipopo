#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
XMPP shell: XMPP interface for the Pelix shell

This module depends on the sleekxmpp package: http://sleekxmpp.com/

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

import argparse
import collections
import logging
import queue
import sys
import threading
import time
from io import StringIO
from typing import Any, cast

from slixmpp.jid import JID

import pelix.framework
import pelix.misc.xmpp
import pelix.shell
from pelix.ipopo.constants import use_ipopo
from pelix.ipopo.decorators import ComponentFactory, HiddenProperty, Invalidate, Property, Requires, Validate
from pelix.security import Secret, Subject
from pelix.shell import beans
from pelix.shell.console import handle_common_arguments, make_common_parser
from pelix.utilities import EventData, StreamBase, remove_duplicates

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = [
    "DEFAULT_IDLE_TIMEOUT",
    "DEFAULT_MAX_SESSIONS",
    "METHOD_JID",
    "PROP_IDLE_TIMEOUT",
    "PROP_MAX_SESSIONS",
    "PROP_USERS",
    "STOP_TIMEOUT",
    "TRANSPORT",
    "main",
]

# ------------------------------------------------------------------------------

# Logger
_logger = logging.getLogger(__name__)

PROP_USERS = "shell.xmpp.users"
"""
Component property: who may use the shell, as a dictionary associating a bare JID to a user
name of the security layer. Default: nobody
"""

PROP_IDLE_TIMEOUT = "shell.xmpp.idle_timeout"
"""
Component property: seconds a session waits for a command, or for the answer to a command
asking for input, before it ends. Default: 3600. 0: never
"""

PROP_MAX_SESSIONS = "shell.xmpp.max_sessions"
"""
Component property: maximum number of simultaneous sessions of a JID, one per resource, so that a
user can't take the sessions of the others. Default: 4. 0: no limit
"""

DEFAULT_IDLE_TIMEOUT = 3600
DEFAULT_MAX_SESSIONS = 4

STOP_TIMEOUT = 2.0
""" Seconds the stop of the shell waits for the commands of the sessions to end """

TRANSPORT = "xmpp"
""" Transport name of the subjects of the XMPP shell """

METHOD_JID = "jid"
""" Authentication method of the XMPP shell: the XMPP server authenticated the sender """

_NS_DELAY = "{urn:xmpp:delay}delay"
""" Element of a message the server delivers late (XEP-0203): kept offline, or forwarded """

# ------------------------------------------------------------------------------


class _XmppOutStream(StreamBase[str]):
    """
    File-like XMPP output. For shell IOHandler use only
    """

    _MODE = "w"
    _WRITABLE = True

    def __init__(self, client: pelix.misc.xmpp.BasicBot, target: JID) -> None:
        """
        Sets up the stream

        :param client: XMPP client
        :param target: Output target JID
        """
        super().__init__()
        self._client: pelix.misc.xmpp.BasicBot = client
        self._target: JID = target
        self._buffer: StringIO = StringIO()

        # Indicate to the I/O handler that we want strings, not bytes
        self.encoding: str = "utf-8"

    def close(self) -> None:
        """
        Sends pending data then closes the stream
        """
        if not self._closed:
            try:
                self.flush()
            finally:
                super().close()

    def write(self, data: str) -> int:
        """
        Writes data to a buffer
        """
        self._check_open()
        self._buffer.write(data)
        return len(data)

    def flush(self) -> None:
        """
        Sends buffered data to the target
        """
        self._check_open()

        # Flush buffer
        content = self._buffer.getvalue()
        self._buffer = StringIO()

        if content:
            # Send message
            try:
                self._client.send_message(mto=self._target, mbody=content, mtype="chat")
            except Exception:
                _logger.exception("Error while sending message")
                raise


class _XmppInStream(StreamBase[str]):
    """
    File-like XMPP input. For shell IOHandler use only
    """

    _MODE = "r"
    _READABLE = True

    def __init__(self, xmpp_ui: "IPopoXMPPShell", source_jid: JID) -> None:
        """
        Sets up the object

        :param xmpp_ui: The IPopoXMPPShell object
        :param source_jid: Client JID
        """
        super().__init__()
        self._ui = xmpp_ui
        self._jid = source_jid

    def read(self, size: int = -1) -> str:
        """
        Waits for the next message from the XMPP client

        :param size: Maximum number of characters to return (no limit if negative)
        :return: The message, or an empty string at the end of the stream
        """
        return self.readline(size)

    def readline(self, limit: int = -1) -> str:
        """
        Waits for a line from the XMPP client

        :param limit: Maximum number of characters to return (no limit if negative)
        :return: The line, or an empty string at the end of the stream
        """
        self._check_open()

        # Wait for content from the user
        content = self._ui.read_from(self._jid) or ""
        if limit < 0:
            # A negative slice bound would cut the end of the message
            return content
        return content[:limit]


# ------------------------------------------------------------------------------


class _XmppSession:
    """
    The shell session of a full JID, and the commands its thread runs in order
    """

    def __init__(self, shell_session: beans.ShellSession) -> None:
        self.shell_session = shell_session
        # None: the end of the session
        self.commands: queue.SimpleQueue[str | None] = queue.SimpleQueue()
        self.thread: threading.Thread | None = None


@ComponentFactory(pelix.shell.FACTORY_XMPP_SHELL)
@Requires("_shell", pelix.shell.ShellService)
@Property("_host", "shell.xmpp.server", "localhost")
@Property("_port", "shell.xmpp.port", 5222)
@Property("_jid", "shell.xmpp.jid")
@HiddenProperty("_password", "shell.xmpp.password")
@Property("_use_tls", "shell.xmpp.tls", "1")
@Property("_use_ssl", "shell.xmpp.ssl", "0")
@Property("_tls_verify", "shell.xmpp.tls.verify", "1")
@Property("_users", PROP_USERS, None)
@Property("_idle_timeout", PROP_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT)
@Property("_max_sessions", PROP_MAX_SESSIONS, DEFAULT_MAX_SESSIONS)
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
        self._jid: str | None = None
        self._password: Secret[str] | None = None
        self._use_tls: bool = True
        self._use_ssl: bool = False
        self._tls_verify: bool = True
        self._users: Any = None
        self._idle_timeout: Any = DEFAULT_IDLE_TIMEOUT
        self._max_sessions: Any = DEFAULT_MAX_SESSIONS

        # Normalized limits (None: no limit)
        self.__idle_timeout: int | None = DEFAULT_IDLE_TIMEOUT
        self.__max_sessions: int | None = DEFAULT_MAX_SESSIONS

        # XMPP Bot
        self.__bot: pelix.misc.xmpp.BasicBot | None = None

        # Shell sessions, each with its own thread: a command waiting for input only
        # blocks its own session
        self.__sessions: dict[JID, _XmppSession] = {}

        # Waiting for a message from the given JID
        self.__waiting: dict[JID, collections.deque[EventData[str]]] = {}

        # Protects the sessions and the waits, shared by the XMPP and session threads
        self.__lock = threading.Lock()

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
        self._tls_verify = bool(self.__normalize_int(self._tls_verify, 1))
        # 0 or less: no limit
        self.__idle_timeout = max(0, self.__normalize_int(self._idle_timeout, DEFAULT_IDLE_TIMEOUT)) or None
        self.__max_sessions = max(0, self.__normalize_int(self._max_sessions, DEFAULT_MAX_SESSIONS)) or None

        # Check other values
        if not self._host:
            _logger.error("No XMPP server host given. Abandon.")
            raise ValueError("No XMPP server host given")

        if not self._jid or not self._password:
            _logger.error("No JID or password given. Abandon.")
            raise ValueError("No JID or password given")

        users = self.__get_users()
        if JID(self._jid).bare in users:
            # Anyone with the password of the bot could then use the shell as that user
            raise ValueError(f"The JID of the bot can't be a user of the shell: {self._jid}")

        if not users:
            _logger.warning("No user given in %s: the XMPP shell will answer nobody", PROP_USERS)

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
        self.__bot = pelix.misc.xmpp.BasicBot(self._jid, self._password.reveal(), ssl_verify=self._tls_verify)
        # Handled by __on_subscription_request: only the users see the presence of the bot
        self.__bot.auto_authorize = None

        # Register to events
        self.__bot.add_event_handler("message", self.__on_message)
        self.__bot.add_event_handler("session_start", self.__on_start)
        self.__bot.add_event_handler("session_end", self.__on_end)
        self.__bot.add_event_handler("socket_error", self.__on_error)
        self.__bot.add_event_handler("got_offline", self.__on_offline)
        self.__bot.add_event_handler("roster_subscription_request", self.__on_subscription_request)
        self.__bot.add_event_handler("roster_update", self.__revoke_former_users)
        self.__bot.add_event_handler("presence_available", self.__revoke_former_users)

        # Connect to the server
        self.__bot.connect(self._host, self._port, self._use_tls, self._use_ssl)

    @Invalidate
    def invalidate(self, _: pelix.framework.BundleContext) -> None:
        """
        Component invalidated
        """
        with self.__lock:
            sessions = list(self.__sessions.values())
            waiting = [event for events in self.__waiting.values() for event in events]
            self.__sessions.clear()
            self.__waiting.clear()

        # The threads end after their current command, which gets no more input
        for session in sessions:
            session.commands.put(None)
        for event in waiting:
            event.set(None)

        # Waited for before the bot goes, so that a command can still send its output
        deadline = time.monotonic() + STOP_TIMEOUT
        for session in sessions:
            thread = session.thread
            if thread is not None and thread is not threading.current_thread():
                # Not the session of a command stopping the shell: it can't wait for itself
                thread.join(max(0.0, deadline - time.monotonic()))
                if thread.is_alive():
                    _logger.warning("A command of the XMPP shell is still running: %s", thread.name)

        if self.__bot is not None:
            # Disconnect the bot
            self.__bot.disconnect()
            self.__bot = None

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

    def __on_offline(self, data: dict[str, Any]) -> None:
        """
        XMPP client got offline: its session ends
        :param data: Message stanza
        """
        source_jid = data["from"]
        with self.__lock:
            session = self.__sessions.pop(source_jid, None)
            waiting = self.__waiting.pop(source_jid, None)

        if session is None:
            # Ignore unknown JID
            return

        session.commands.put(None)
        for event in waiting or ():
            event.set(None)

        if self.__bot is not None:
            # Unsubscribe to presence events
            self.__bot.send_presence(pto=source_jid, ptype="unsubscribe")
        else:
            _logger.debug("No XMPP bot: cannot unsubscribe %s", source_jid)

    def __on_subscription_request(self, presence: Any) -> None:
        """
        A JID asks to see the presence of the bot: only granted to the users of the shell,
        which still gives no access, as the users are checked on each message.

        Called in the thread of the XMPP client, which owns the roster.

        :param presence: The subscription request
        """
        sender = cast(JID, presence["from"])
        item = presence.stream.roster[presence["to"]][sender]
        if sender.bare != JID(self._jid).bare and sender.bare in self.__get_users():
            item.authorize()
        else:
            _logger.info("Refusing the presence subscription of %s, which is not a user of the shell", sender)
            item.unauthorize()

    def __revoke_former_users(self, stanza: Any) -> None:
        """
        Revokes the presence subscriptions of the JIDs which are no longer users of the
        shell. No property change reaches the component, so this is checked when the
        roster arrives, and at each presence and each message of another JID.

        Called in the thread of the XMPP client, which owns the roster.

        :param stanza: The stanza which triggered the check
        """
        roster = stanza.stream.client_roster
        users = self.__get_users()
        bot = JID(self._jid).bare
        for jid in list(roster):
            bare = JID(jid).bare
            item = roster[jid]
            if item["from"] and (bare == bot or bare not in users):
                _logger.info(
                    "Revoking the presence subscription of %s, which is not a user of the shell", jid
                )
                item.unauthorize()

    def __on_message(self, data: dict[str, Any]) -> None:
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
            sender = cast(JID, data["from"])
            user = self.__get_user(sender, data) if body else None
            if user is None:
                self.__revoke_former_users(data)
                return

            with self.__lock:
                session = self.__sessions.get(sender)
                waiting = self.__waiting.get(sender)
                if waiting and session is not None and session.shell_session.subject.name == user:
                    # The answer to a command waiting for input
                    waiting.popleft().set(body)
                    if not waiting:
                        del self.__waiting[sender]
                    return

                self.__enqueue(sender, user, body)

    def __get_user(self, sender: JID, data: Any) -> str | None:
        """
        Finds the user of the shell who sent a message. Checked before anything else,
        including the answer to a command waiting for input.

        The XMPP server, and the servers it federates with, authenticate the sender.

        :param sender: The JID of the sender
        :param data: The message stanza
        :return: The user name, or None to ignore the message
        """
        user = self.__get_users().get(sender.bare) if sender.bare != JID(self._jid).bare else None
        if user is None:
            _logger.info(
                "Ignoring a message from %s, which is not a user of the shell", sender.bare or "nobody"
            )
        elif data.xml.find(_NS_DELAY) is not None:
            # A command sent long ago, maybe by someone who is no longer allowed to
            _logger.warning("Ignoring a delayed message from %s", sender)
            return None

        return user

    def __get_users(self) -> dict[str, str]:
        """
        Reads the users of the shell, at each use: a user removed by a reconfiguration of
        the component loses the shell at once

        :return: The user names, by bare JID, normalized as the server writes the senders
        """
        return {JID(jid).bare: str(name) for jid, name in dict(self._users or {}).items()}

    def __enqueue(self, sender: JID, user: str, content: str) -> None:
        """
        Gives a command to the session of its sender, started if necessary. Call it
        with the lock held

        :param sender: The full JID of the sender
        :param user: Its user name
        :param content: The command line
        """
        session = self.__sessions.get(sender)
        if session is not None and session.shell_session.subject.name != user:
            # Associated to another user since: start again, the new user mustn't answer
            # what the previous one was asked
            self.__sessions.pop(sender).commands.put(None)
            for event in self.__waiting.pop(sender, ()):
                event.set(None)
            session = None

        if session is None:
            if self.__bot is None:
                _logger.error("No XMPP bot: cannot handle message")
                return

            count = sum(1 for jid in self.__sessions if jid.bare == sender.bare)
            if self.__max_sessions is not None and count >= self.__max_sessions:
                _logger.warning(
                    "Ignoring a command of %s: already %d sessions for %s", sender, count, sender.bare
                )
                return

            # Subscribe to presence messages, to end the session when the client goes offline
            self.__bot.send_presence(pto=sender, ptype="subscribe")

            session = self.__sessions[sender] = _XmppSession(
                beans.ShellSession(
                    beans.IOHandler(_XmppInStream(self, sender), _XmppOutStream(self.__bot, sender)),
                    {"xmpp.jid": sender},
                    Subject(user, authenticated=True, method=METHOD_JID, transport=TRANSPORT),
                )
            )
            session.thread = threading.Thread(
                target=self.__run_session, args=(sender, session), name=f"XMPPShell-{sender}", daemon=True
            )
            session.thread.start()

        session.commands.put(content)

    def __run_session(self, jid: JID, session: _XmppSession) -> None:
        """
        Runs the commands of a session in order, until it ends or stays idle too long

        :param jid: The full JID of the session
        :param session: The session
        """
        while True:
            try:
                content = session.commands.get(timeout=self.__idle_timeout)
            except queue.Empty:
                with self.__lock:
                    if not session.commands.empty():
                        # Given while the wait ended
                        continue

                    if self.__sessions.get(jid) is session:
                        del self.__sessions[jid]

                _logger.info("Closing the idle XMPP shell session of %s", jid)
                return

            if content is None:
                return

            if self.__get_users().get(jid.bare) != session.shell_session.subject.name:
                # Removed, or associated to another user, since the message came
                continue

            try:
                self._shell.execute(content, session.shell_session)
            except KeyboardInterrupt:
                # The "exit" and "quit" commands
                with self.__lock:
                    if self.__sessions.get(jid) is session:
                        del self.__sessions[jid]
                return
            except Exception:
                _logger.exception("Error running a command of %s", jid)

    def read_from(self, jid: JID) -> str | None:
        """
        Returns the next message read from the given JID

        :param jid: Source JID
        :return: The next content sent by this JID, or None if it sent nothing in time
        """
        # Prepare an event
        event = EventData[str]()
        with self.__lock:
            self.__waiting.setdefault(jid, collections.deque()).append(event)

        if not event.wait(self.__idle_timeout):
            with self.__lock:
                waiting = self.__waiting.get(jid)
                if waiting is not None and event in waiting:
                    waiting.remove(event)
                    if not waiting:
                        del self.__waiting[jid]

            if not event.is_set():
                # A removed user, or one who left: the command reads an end of input
                _logger.info("No answer from %s in time: ending its input", jid)
                return None

        # Return the message content
        return event.data


# ------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
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
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use a STARTTLS connection",
    )
    group.add_argument(
        "--ssl",
        dest="use_ssl",
        action="store_true",
        help="Use an SSL connection",
    )
    group.add_argument(
        "-u",
        "--user",
        dest="users",
        action="append",
        metavar="JID=NAME",
        help="Allow this JID to use the shell, as this user of the security layer (repeatable)",
    )
    group.add_argument(
        "--tls-verify",
        dest="tls_verify",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Verify the certificate of the XMPP server",
    )

    # Parse them
    args = parser.parse_args(argv)
    users: dict[str, str] = {}
    for user in args.users or ():
        jid, sep, name = user.partition("=")
        if not sep or not jid or not name:
            parser.error(f"Invalid --user {user!r}: expected JID=NAME")
        users[jid] = name

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
        "pelix.security.core",
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
                "shell.xmpp.tls.verify": args.tls_verify,
                PROP_USERS: users,
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
