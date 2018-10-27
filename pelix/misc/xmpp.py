#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
XMPP bot classes: Small classes inheriting from SleekXMPP to ease the
development of bots in Pelix

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

# XMPP, based on SleekXMPP
import sleekxmpp

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class BasicBot(sleekxmpp.ClientXMPP):
    """
    Basic bot: connects to a server with the given credentials
    """

    def __init__(self, jid, password, initial_priority=0):
        """
        Sets up the robot

        :param jid: Full Jabber ID of the bot
        :param password: Account password
        :param initial_priority: Initial presence priority
        """
        # Set up the client
        sleekxmpp.ClientXMPP.__init__(self, jid, password)

        # Store parameters
        self._initial_priority = initial_priority

        # Register the plug-ins: Form and Ping
        self.register_plugin("xep_0004")
        self.register_plugin("xep_0199")

        # Register to session start event
        self.add_event_handler("session_start", self.on_session_start)

    def connect(
        self, host, port=5222, reattempt=False, use_tls=True, use_ssl=False
    ):
        # pylint: disable=W0221
        """
        Connects to the server.

        By default, uses an un-encrypted connection, as it won't connect to an
        OpenFire server otherwise

        :param host: Server host name
        :param port: Server port (default: 5222)
        :param reattempt: If True, tries to connect to the server until it
                         succeeds
        :param use_tls: Use STARTTLS
        :param use_ssl: Server connection is encrypted
        :return: True if connection succeeded
        """
        if not self._expected_server_name:
            # We seem to connect the server anonymously, so SleekXMPP
            # couldn't find the server host name from the JID
            # => give it the given server host name as the expected one
            self._expected_server_name = host

        # Try to connect
        if super(BasicBot, self).connect(
            (host, port), reattempt, use_tls, use_ssl
        ):
            # On success, start the processing thread
            self.process(threaded=True)
            return True

        return False

    def on_session_start(self, data):
        # pylint: disable=W0613
        """
        XMPP session started
        """
        # Send initial presence
        self.send_presence(ppriority=self._initial_priority)

        # Request roster
        self.get_roster()


# ------------------------------------------------------------------------------


class InviteMixIn(sleekxmpp.BaseXMPP):
    """
    A bot that automatically accepts invites from other participants
    """

    def __init__(self, nick):
        # pylint: disable=W0231
        """
        Sets up the Mix-in

        :param nick: Nickname to use in rooms
        """
        # Store nick
        self._nick = nick

        # Register the Multi-User Chat plug-in
        self.register_plugin("xep_0045")

        # Activate the plug-in
        self.invite_start()

    def invite_start(self):
        """
        Activates the mix-in.
        """
        self.add_event_handler("groupchat_invite", self.on_invite)

    def invite_stop(self):
        """
        Deactivates the mix-in
        """
        self.del_event_handler("groupchat_invite", self.on_invite)

    def on_invite(self, data):
        """
        Multi-User Chat invite
        """
        if not self._nick:
            self._nick = self.boundjid.user

        # Join the room
        self.plugin["xep_0045"].joinMUC(data["from"], self._nick)


# ------------------------------------------------------------------------------


class ServiceDiscoveryMixin(sleekxmpp.BaseXMPP):
    """
    Adds utility methods to a bot to look for services
    """

    def __init__(self):
        # pylint: disable=W0231
        """
        Sets up the Mix-in
        """
        # Register the ServiceDiscovery plug-in
        self.register_plugin("xep_0030")

    def iter_services(self, feature=None):
        """
        Iterates over the root-level services on the server which provides the
        requested feature

        :param feature: Feature that the service must provide (optional)
        :return: A generator of services JID
        """
        # Get the list of root services
        items = self["xep_0030"].get_items(
            jid=self.boundjid.domain,
            ifrom=self.boundjid.full,
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
                info = self["xep_0030"].get_info(
                    jid=item[0],
                    ifrom=self.boundjid.full,
                    block=True,
                    timeout=10,
                )
                if feature in info["disco_info"]["features"]:
                    # The service provides the required feature
                    yield item[0]
