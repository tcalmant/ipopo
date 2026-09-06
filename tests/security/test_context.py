#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the current subject of the Pelix security package: the context variable,
get_current_subject() and run_as().

:author: Thomas Calmant
"""

import asyncio
import contextvars
import threading
import unittest

from pelix.security import _SUBJECT, ANONYMOUS, Subject, get_current_subject, run_as

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------

ALICE = Subject("alice", roles=frozenset({"admin"}), authenticated=True)
BOB = Subject("bob", roles=frozenset({"operator"}), authenticated=True)

# ------------------------------------------------------------------------------


class CurrentSubjectTest(unittest.TestCase):
    """
    Tests get_current_subject() and run_as()
    """

    def test_nothing_published_is_anonymous(self) -> None:
        """
        The default is the anonymous subject, not None: a caller never has to guard
        """
        self.assertIs(get_current_subject(), ANONYMOUS)

    def test_run_as_publishes_and_restores(self) -> None:
        with run_as(ALICE):
            self.assertIs(get_current_subject(), ALICE)

        self.assertIs(get_current_subject(), ANONYMOUS)

    def test_run_as_nests(self) -> None:
        with run_as(ALICE):
            with run_as(BOB):
                self.assertIs(get_current_subject(), BOB)

            self.assertIs(get_current_subject(), ALICE)

        self.assertIs(get_current_subject(), ANONYMOUS)

    def test_run_as_restores_on_exception(self) -> None:
        """
        The reset lives in a finally: an escaping exception must not leave an identity
        published behind it
        """
        with self.assertRaises(ValueError), run_as(ALICE):
            raise ValueError("boom")

        self.assertIs(get_current_subject(), ANONYMOUS)


class PropagationTest(unittest.TestCase):
    """
    The current subject follows the standard Python context: wherever a context
    propagates, the subject propagates, and nowhere else
    """

    def test_a_copied_context_carries_it(self) -> None:
        with run_as(ALICE):
            context = contextvars.copy_context()

        self.assertEqual(context.run(get_current_subject), ALICE)

    def test_a_bare_thread_starts_anonymous(self) -> None:
        """
        A new thread starts with an empty context, so code crossing that boundary copies
        it explicitly. Stated as a test, because the failure is silent otherwise
        """
        seen: list[Subject] = []

        with run_as(ALICE):
            thread = threading.Thread(target=lambda: seen.append(get_current_subject()))
            thread.start()
            thread.join()

        self.assertIs(seen[0], ANONYMOUS)

    def test_a_thread_running_a_copied_context_carries_it(self) -> None:
        """
        And the explicit copy is what fixes it
        """
        seen: list[Subject] = []

        with run_as(ALICE):
            context = contextvars.copy_context()
            thread = threading.Thread(target=lambda: seen.append(context.run(get_current_subject)))
            thread.start()
            thread.join()

        self.assertEqual(seen[0], ALICE)

    def test_a_task_inherits_the_context_of_its_creator(self) -> None:
        async def read() -> Subject:
            return get_current_subject()

        async def main() -> tuple[Subject, Subject]:
            with run_as(ALICE):
                inside = await asyncio.create_task(read())

            outside = await asyncio.create_task(read())
            return inside, outside

        inside, outside = asyncio.run(main())
        self.assertEqual(inside, ALICE)
        self.assertIs(outside, ANONYMOUS)

    def test_a_task_does_not_publish_back_to_its_creator(self) -> None:
        """
        A Task runs in a copy, so an identity it publishes and never takes back stays
        inside it
        """

        async def elevate() -> None:
            # Deliberately without the reset run_as() would do
            _SUBJECT.set(BOB)

        async def main() -> Subject:
            with run_as(ALICE):
                await asyncio.create_task(elevate())
                return get_current_subject()

        self.assertEqual(asyncio.run(main()), ALICE)


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
