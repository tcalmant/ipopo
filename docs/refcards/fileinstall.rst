File Install
############

Pelix provides a File Install utility service, provided by the
``pelix.services.fileinstall`` bundle.

The service will wait for listeners, each indicating the folder it wants to
observe in its ``fileinstall.folder`` property.
File Install will poll every second the state of each requested folder and
notify the associated listeners of any file change (addition, update and
deletion).
It was decided early on to use a second-based polling approach as it works on
all systems.

Listeners registration
======================

The FileInstall service provides the :class:`pelix.services.FileInstall`
specification to un/register listeners.

It also supports the whiteboard pattern: listeners can be registered by
providing the :class:`pelix.services.FileInstallListener` specification.
Each listener service must hold a ``fileinstall.folder`` string property,
containing the path of the folder to observe.
Only one folder can be observed by a listener.

API
===

.. autoclass:: pelix.services.FileInstall
   :members:

.. autoclass:: pelix.services.FileInstallListener
   :members:
