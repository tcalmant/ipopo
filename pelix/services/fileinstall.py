#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
FileInstall: Polls for changes on files in a directory and notifies listeners

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

import logging
import os
import threading
import zlib
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, cast

import pelix.services as services
import pelix.threadpool
from pelix.framework import BundleContext
from pelix.internals.registry import ServiceReference
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Instantiate,
    Invalidate,
    Property,
    Provides,
    Requires,
    UnbindField,
    UpdateField,
    Validate,
)

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


@ComponentFactory()
@Provides(services.FileInstall)
@Requires(
    "_listeners",
    services.FileInstallListener,
    aggregate=True,
    optional=True,
)
@Property("_poll_time", "poll.time", 1)
@Instantiate("pelix-services-file-install")
class FileInstall(services.FileInstall):
    """
    Polls folders to look for files modifications
    """

    # Listeners (injected)
    _listeners: List[services.FileInstallListener]

    def __init__(self) -> None:
        """
        Sets up members
        """
        # Folder -> [listeners] (computed)
        self._folder_listeners: Dict[str, Set[services.FileInstallListener]] = {}

        # Polling delta time (1 second by default)
        self._poll_time = 1

        # Lock
        self.__lock = threading.RLock()

        # Single thread task pool to notify listeners
        self.__pool = pelix.threadpool.ThreadPool(1, logname="FileInstallNotifier")

        # 1 thread per watched folder (folder -> Thread)
        self.__threads: Dict[str, threading.Thread] = {}

        # Thread stoppers (folder -> Event)
        self.__stoppers: Dict[str, threading.Event] = {}

    @Validate
    def _validate(self, context: BundleContext) -> None:
        """
        Component validated
        """
        with self.__lock:
            # Start the task pool
            self.__pool.start()

    @Invalidate
    def _invalidate(self, context: BundleContext) -> None:
        """
        Component invalidated
        """
        with self.__lock:
            # Stop all threads
            for event in set(self.__stoppers.values()):
                event.set()

            # Wait for them
            for thread in set(self.__threads.values()):
                thread.join()

            # Stop the task pool
            self.__pool.stop()

            # Clean up
            self.__stoppers.clear()
            self.__threads.clear()

    @BindField("_listeners")
    def _bind_listener(
        self,
        field: str,
        svc: services.FileInstallListener,
        svc_ref: ServiceReference[services.FileInstallListener],
    ) -> None:
        """
        A new listener is bound
        """
        with self.__lock:
            folder = cast(Optional[str], svc_ref.get_property(services.PROP_FILEINSTALL_FOLDER))
            if folder:
                # Register the listener for this service
                self.add_listener(folder, svc)

    @UpdateField("_listeners")
    def _update_field(
        self,
        field: str,
        svc: services.FileInstallListener,
        svc_ref: ServiceReference[services.FileInstallListener],
        old_props: Optional[Dict[str, Any]],
    ) -> None:
        """
        A bound listener has been updated
        """
        with self.__lock:
            old_folder = (old_props or {}).get(services.PROP_FILEINSTALL_FOLDER)
            new_folder = svc_ref.get_property(services.PROP_FILEINSTALL_FOLDER)

            if old_folder != new_folder:
                # Folder changed
                if old_folder:
                    self.remove_listener(old_folder, svc)

                if new_folder:
                    self.add_listener(new_folder, svc)

    @UnbindField("_listeners")
    def _unbind_listener(
        self,
        field: str,
        svc: services.FileInstallListener,
        svc_ref: ServiceReference[services.FileInstallListener],
    ) -> None:
        """
        A listener is gone
        """
        with self.__lock:
            folder = svc_ref.get_property(services.PROP_FILEINSTALL_FOLDER)
            if folder:
                # Remove the listener
                self.remove_listener(folder, svc)

    def add_listener(self, folder: str, listener: services.FileInstallListener) -> bool:
        """
        Manual registration of a folder listener

        :param folder: Path to the folder to watch
        :param listener: Listener to register
        :return: True if the listener has been registered
        """
        with self.__lock:
            # Simply add the listener
            if folder:
                try:
                    listeners = self._folder_listeners[folder]
                except KeyError:
                    # Unknown folder
                    listeners = self._folder_listeners[folder] = set()

                    # Start a new thread
                    event = self.__stoppers[folder] = threading.Event()
                    thread = threading.Thread(
                        target=self.__watch,
                        args=(folder, event),
                        name=f"FileInstall-{folder}",
                    )
                    thread.daemon = True
                    self.__threads[folder] = thread
                    thread.start()

                listeners.add(listener)
                return True

            return False

    def remove_listener(self, folder: str, listener: services.FileInstallListener) -> None:
        """
        Manual unregistration of a folder listener.

        :param folder: Path to the folder the listener watched
        :param listener: Listener to unregister
        :raise ValueError: The listener wasn't watching this folder
        """
        with self.__lock:
            # Remove the listener
            listeners = self._folder_listeners[folder]
            listeners.remove(listener)
            if not listeners:
                try:
                    # Stop the corresponding thread
                    self.__stoppers.pop(folder).set()

                except KeyError:
                    # Component invalidated
                    pass

                else:
                    # Wait for the thread to stop
                    self.__threads.pop(folder).join()

                    # No more listener for this folder
                    del self._folder_listeners[folder]

    def __notify(
        self, folder: str, added: Iterable[str], updated: Iterable[str], deleted: Iterable[str]
    ) -> None:
        """
        Notifies listeners that files of a folder has been modified

        :param folder: Folder where changes occurred
        :param added: Names of added files
        :param updated: Names of modified files
        :param deleted: Names of removed files
        """
        with self.__lock:
            try:
                # Get a copy of the listeners for this folder
                listeners = self._folder_listeners[folder].copy()
            except KeyError:
                # No (more) listeners: do nothing
                return

        for listener in listeners:
            try:
                listener.folder_change(folder, added, updated, deleted)
            except Exception as ex:
                _logger.exception("Error notifying a folder listener: %s", ex)

    @staticmethod
    def __get_checksum(filepath: str) -> int:
        """
        Returns the checksum (Adler32) of the given file

        :param filepath: Path to the file
        :return: The checksum (int) of the given file
        :raise OSError: File not accessible
        :raise IOError: File not readable
        """
        # Don't forget to open the file in binary mode
        with open(filepath, "rb") as filep:
            # Return the checksum of the given file
            return zlib.adler32(filep.read())

    def __get_file_info(self, folder: str, filename: str) -> Tuple[float, int]:
        """
        Returns the (mtime, checksum) tuple for the given file

        :param folder: Path to the parent folder
        :param filename: Base name of the file
        :return: A tuple containing file information
        :raise OSError: File not accessible
        :raise IOError: File not readable
        """
        filepath = os.path.join(folder, filename)
        return os.path.getmtime(filepath), self.__get_checksum(filepath)

    def __check_different(
        self, folder: str, filename: str, file_info: Tuple[float, int], updated: Set[str]
    ) -> Tuple[float, int]:
        """
        Checks if the given file has changed since the previous check

        :param folder: Path to the parent folder
        :param filename: Base name of the file
        :param file_info: Current information about the file
        :param updated: Set of updated files, where the file name might be added
        :return: The (updated) file information tuple
        :raise OSError: File not accessible
        :raise IOError: File not readable
        """
        # Compute the file path
        filepath = os.path.join(folder, filename)

        # Get the previous modification time
        previous_mtime = file_info[0]

        # Get the new modification time
        mtime = os.path.getmtime(filepath)

        if previous_mtime == mtime:
            # No modification (no need to compute the checksum)
            return file_info

        # Get the previous checksum
        previous_checksum = file_info[1]

        # Compute the new one
        checksum = self.__get_checksum(filepath)

        if previous_checksum == checksum:
            # No real modification, update file info
            return mtime, checksum

        # File modified
        updated.add(filename)
        return mtime, checksum

    def __watch(self, folder: str, stopper: threading.Event) -> None:
        """
        Loop that looks for changes in the given folder

        :param folder: Folder to watch
        :param stopper: An Event object that will stop the loop once set
        """
        # File name -> (modification time, checksum)
        previous_info: Dict[str, Tuple[float, int]] = {}

        while not stopper.wait(self._poll_time) and not stopper.is_set():
            if not os.path.exists(folder):
                # Nothing to do yet
                continue

            # Look for files
            filenames = {
                filename for filename in os.listdir(folder) if os.path.isfile(os.path.join(folder, filename))
            }

            # Prepare the sets
            added: Set[str] = set()
            updated: Set[str] = set()
            deleted: Set[str] = set(previous_info.keys()).difference(filenames)

            # Compute differences
            for filename in filenames:
                try:
                    # Get previous information
                    file_info = previous_info[filename]
                except KeyError:
                    # Unknown file: added one
                    added.add(filename)
                    previous_info[filename] = self.__get_file_info(folder, filename)
                else:
                    try:
                        # Known file name
                        new_info = self.__check_different(folder, filename, file_info, updated)
                        # Store new information
                        previous_info[filename] = new_info
                    except (IOError, OSError):
                        # Error reading file, do nothing
                        pass

            # Remove information about deleted files
            for filename in deleted:
                del previous_info[filename]

            if added or updated or deleted:
                # Something changed: notify listeners
                self.__pool.enqueue(self.__notify, folder, added, updated, deleted)
