#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the configuration of the XMPP shell interface.

Unlike test_xmpp.py, this module doesn't need a live XMPP server: the bot is
replaced by a recording stub, so the wiring of the component properties can be
checked anywhere.

:author: Thomas Calmant
"""

import unittest
from typing import Any
from unittest import mock

try:
    import pelix.misc.xmpp
    import pelix.shell.xmpp
except ImportError:
    # Missing requirement: not a fatal error
    raise unittest.SkipTest("XMPP client dependency missing: skip test")

from pelix.framework import FrameworkFactory
from pelix.ipopo.constants import use_ipopo
from pelix.shell import FACTORY_XMPP_SHELL

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class _FakeBot:
    """
    Records how the bot was constructed and swallows everything else
    """

    def __init__(self, jid: Any, password: Any, **kwargs: Any) -> None:
        self.jid = jid
        self.password = password
        self.kwargs = kwargs
        self.auto_authorize: bool = False

    def add_event_handler(self, *_: Any, **__: Any) -> None:
        pass

    def connect(self, *_: Any, **__: Any) -> bool:
        return True

    def disconnect(self, *_: Any, **__: Any) -> None:
        pass


class XMPPShellConfigTest(unittest.TestCase):
    """
    Tests the properties of the XMPP shell component
    """

    def setUp(self) -> None:
        """
        Starts a framework with the XMPP shell bundle
        """
        self.framework = FrameworkFactory.get_framework()
        self.addCleanup(FrameworkFactory.delete_framework)
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        self.context.install_bundle("pelix.ipopo.core").start()
        self.context.install_bundle("pelix.shell.core").start()
        self.context.install_bundle("pelix.shell.xmpp").start()

    def instantiate(self, properties: dict[str, Any]) -> _FakeBot:
        """
        Instantiates the XMPP shell with the given properties and returns the
        stub bot it created

        :param properties: Component properties
        :return: The recording bot stub
        """
        props: dict[str, Any] = {
            "shell.xmpp.jid": "bot@localhost",
            "shell.xmpp.password": "foobar",
        }
        props.update(properties)

        with (
            mock.patch.object(pelix.misc.xmpp, "BasicBot", _FakeBot),
            use_ipopo(self.context) as ipopo,
        ):
            component = ipopo.instantiate(FACTORY_XMPP_SHELL, "xmpp-shell", props)

        # Name-mangled private attribute of IPopoXMPPShell
        bot = component._IPopoXMPPShell__bot  # type: ignore[attr-defined]
        assert isinstance(bot, _FakeBot)
        return bot

    def test_tls_verify_disabled_by_default(self) -> None:
        """
        The certificate of the server is not verified by default (3.2.x)
        """
        bot = self.instantiate({})
        self.assertFalse(bot.kwargs["ssl_verify"])

    def test_tls_verify_enabled(self) -> None:
        """
        The shell.xmpp.tls.verify property reaches the bot
        """
        bot = self.instantiate({"shell.xmpp.tls.verify": "1"})
        self.assertTrue(bot.kwargs["ssl_verify"])

    def test_tls_verify_explicitly_disabled(self) -> None:
        """
        The shell.xmpp.tls.verify property can be set to 0 explicitly
        """
        bot = self.instantiate({"shell.xmpp.tls.verify": "0"})
        self.assertFalse(bot.kwargs["ssl_verify"])

    def test_tls_verify_invalid_value(self) -> None:
        """
        An unparsable value falls back to the default (no verification)
        """
        bot = self.instantiate({"shell.xmpp.tls.verify": "yes please"})
        self.assertFalse(bot.kwargs["ssl_verify"])


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
