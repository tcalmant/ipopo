#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Folder Watcher: Polls for changes on files in a directory

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: Apache License 2.0
:version: 0.1
:status: Beta

..

    Copyright 2013 isandlaTech

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
__version_info__ = (0, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

#-------------------------------------------------------------------------------

# Pelix
from pelix.ipopo.decorators import ComponentFactory, Provides, Requires, \
    Validate, Invalidate, Instantiate, BindField, UnbindField, UpdateField
import pelix.services as services
import pelix.threadpool

# Standard library
import logging
import os
import threading
import zlib

#-------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

#-------------------------------------------------------------------------------

@ComponentFactory()
@Provides(services.SERVICE_FILEINSTALL)
@Requires('_listeners', services.SERVICE_FILEINSTALL_LISTENERS,
          aggregate=True, optional=True)
@Instantiate('pelix-services-file-install')
class FolderWatcher(object):
    """
    Polls folders to look for files modifications
    """
    def __init__(self):
        """
        Sets up members
        """
        # Listeners (injected)
        self._listeners = []

        # Folder -> [listeners] (computed)
        self._folder_listeners = {}

        # Lock
        self.__lock = threading.RLock()

        # Single thread task pool to notify listeners
        self.__pool = pelix.threadpool.ThreadPool(1, "FileInstallNotification")

        # 1 thread per watched folder (folder -> Thread)
        self.__threads = {}

        # Thread stoppers (folder -> Event)
        self.__stoppers = {}

        # Validation flag
        self.__validated = False


    @Validate
    def _validate(self, context):
        """
        Component validated
        """
        with self.__lock:
            # Start the task pool
            self.__pool.start()

            # Update the flag
            self.__validated = True


    @Invalidate
    def _invalidate(self, context):
        """
        Component invalidated
        """
        with self.__lock:
            # Update the flag
            self.__validated = False

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


    @BindField('_listeners')
    def _bind_listener(self, _, svc, svc_ref):
        """
        A new listener is bound
        """
        with self.__lock:
            folder = svc_ref.get_property(services.PROP_FILEINSTALL_FOLDER)
            if folder:
                # Register the listener for this service
                self.add_listener(folder, svc)


    @UpdateField('_listeners')
    def _update_field(self, _, svc, svc_ref, old_props):
        """
        A bound listener has been updated
        """
        with self.__lock:
            old_folder = old_props.get(services.PROP_FILEINSTALL_FOLDER)
            new_folder = svc_ref.get_property(services.PROP_FILEINSTALL_FOLDER)

            if old_folder != new_folder:
                # Folder changed
                self.remove_listener(old_folder, svc)
                self.add_listener(new_folder, svc)


    @UnbindField('_listeners')
    def _unbind_listener(self, _, svc, svc_ref):
        """
        A listener is gone
        """
        with self.__lock:
            folder = svc_ref.get_property(services.PROP_FILEINSTALL_FOLDER)
            if folder:
                # Remove the listener
                self.remove_listener(folder, svc)


    def add_listener(self, folder, listener):
        """
        Manual registration of a folder listener

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
                    thread = threading.Thread(target=self.__watch,
                                              args=(folder, event),
                                              name="FolderWatcher-{0}" \
                                                   .format(folder))
                    thread.daemon = True
                    self.__threads[folder] = thread
                    thread.start()

                listeners.add(listener)
                return True

            return False


    def remove_listener(self, folder, listener):
        """
        Manual unregistration of a folder listener
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
                    # Normal behavior
                    self.__threads.pop(folder).join()

                    # No more listener for this folder
                    del self._folder_listeners[folder]


    def __notify(self, folder, added, updated, deleted):
        """
        Notifies listeners that files of a folder has been modified
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


    def __watch(self, folder, stopper):
        """
        Loop that looks for changes in the given folder
        """
        # File name -> Checksum
        previous_checksum = {}

        while not stopper.wait(1) and not stopper.is_set():
            if not os.path.exists(folder):
                # Nothing to do yet
                continue

            # Look for files
            filenames = [filename for filename in os.listdir(folder)
                         if os.path.isfile(os.path.join(folder, filename))]

            # Compute the differences
            added = set()
            updated = set()
            deleted = set(previous_checksum.keys()).difference(filenames)

            for filename in filenames:
                # Get the current time stamp
                try:
                    with open(os.path.join(folder, filename), 'rb') as fp:
                        new_checksum = zlib.adler32(fp.read())

                except IOError:
                    # File unreadable, ignore
                    continue

                try:
                    # Get the previous checksum
                    old_checksum = previous_checksum[filename]

                except KeyError:
                    # File wasn't previously known
                    added.add(filename)
                    previous_checksum[filename] = new_checksum

                else:
                    # Compute the current checksum
                    if old_checksum != new_checksum:
                        # File changed
                        updated.add(filename)
                        previous_checksum[filename] = new_checksum

            # Remove deleted files checksum
            for filename in deleted:
                try:
                    del previous_checksum[filename]
                except KeyError:
                    pass

            if added or updated or deleted:
                # Notify listeners
                self.__pool.enqueue(self.__notify, folder, added, updated,
                                    deleted)
