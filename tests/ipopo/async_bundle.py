#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Bundle with a component having a coroutine @Invalidate callback
"""

import asyncio
import threading

from pelix.framework import BundleContext
from pelix.ipopo.decorators import ComponentFactory, Instantiate, Invalidate

# Thread names of the @Invalidate calls
INVALIDATED: list[str] = []


@ComponentFactory("async-stop-factory")
@Instantiate("async-stop")
class AsyncStop:
    @Invalidate
    async def invalidate(self, context: BundleContext) -> None:
        await asyncio.sleep(0)
        INVALIDATED.append(threading.current_thread().name)
