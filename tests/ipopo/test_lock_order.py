#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests that the iPOPO service takes its internal locks in a consistent order.

:author: Thomas Calmant
"""

import threading
import unittest

from pelix.framework import FrameworkFactory
from pelix.ipopo import decorators
from pelix.ipopo.constants import IPopoEvent, use_ipopo
from tests.ipopo import install_ipopo

# ------------------------------------------------------------------------------

__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------

# Bound of the interleaving waits and of the final joins, in seconds
WAIT = 1
JOIN_TIMEOUT = 10


class LockOrderTest(unittest.TestCase):
    """
    instantiate() and unregister_factory() must not deadlock each other
    """

    def setUp(self):
        self.deadlocked = False
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        self.ipopo = install_ipopo(self.framework)

    def tearDown(self):
        if self.deadlocked:
            # The blocked threads hold the iPOPO locks: stopping the framework would hang too
            return
        self.framework.stop()
        FrameworkFactory.delete_framework()

    def test_instantiate_vs_unregister_factory(self):
        """
        Thread A instantiates a component whose @Validate (run while the instances lock is held)
        instantiates another one; thread B unregisters a factory at the same time.
        Events force the interleaving, the joins are bounded so a regression fails instead of hanging.
        """
        a_validating = threading.Event()
        b_in_unregister = threading.Event()
        context = self.framework.get_bundle_context()

        @decorators.ComponentFactory("validating-factory")
        class Validating:
            @decorators.Validate
            def validate(self, ctx):
                a_validating.set()
                b_in_unregister.wait(WAIT)
                with use_ipopo(ctx) as ipopo:
                    ipopo.instantiate("plain-factory", "b")

        @decorators.ComponentFactory("plain-factory")
        class Plain:
            pass

        @decorators.ComponentFactory("other-factory")
        class Other:
            pass

        class Listener:
            def handle_ipopo_event(self, event):
                if event.get_kind() == IPopoEvent.UNREGISTERED and threading.current_thread().name == "B":
                    b_in_unregister.set()
                    a_validating.wait(WAIT)

        for cls in (Validating, Plain, Other):
            self.ipopo.register_factory(context, cls)
        self.ipopo.add_listener(Listener())

        thread_a = threading.Thread(
            name="A", target=self.ipopo.instantiate, args=("validating-factory", "a"), daemon=True
        )
        thread_b = threading.Thread(
            name="B", target=self.ipopo.unregister_factory, args=("other-factory",), daemon=True
        )
        thread_a.start()
        thread_b.start()
        thread_a.join(JOIN_TIMEOUT)
        thread_b.join(JOIN_TIMEOUT)
        self.deadlocked = thread_a.is_alive() or thread_b.is_alive()
        self.assertFalse(self.deadlocked, "deadlock between instantiate and unregister_factory")


if __name__ == "__main__":
    unittest.main()
