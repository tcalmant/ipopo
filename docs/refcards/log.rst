.. _refcard_log:
.. module:: pelix.misc.log

Logging
=======

The best way to log traces in iPOPO is to use the
`logging <https://docs.python.org/3/library/logging.html>`_ module from the
Python Standad Library.
Pelix/iPOPO relies on this module for its own logs, using a module level
constant providing a logger with the name of the module, like this:

.. code-block:: python

   import logging
   _logger = logging.getLogger(__name__)


That being said, Pelix/iPOPO provides a utility log service matching the OSGi
*LogService* specification, which logs to and reads traces from the standard
Python logging system.

The log service is provided by the ``pelix.misc.log`` bundle. It handles
``LogEntry`` object keeping track of the log timestamp, source bundle and
message. It also registers as a handler to the Python logging system, which
means it can also keep track of all traces logged with the ``logging`` module.


API
---

Once install and started, the ``pelix.misc.log`` bundle provides two services:

* ``pelix.log``: The main log service, which allows to log entries;
* ``pelix.log.reader``: The log reader service, which gives a read-only access
  to previous log entries. Those entries can have stored using either the log
  service or the Python logging system.

Log Service
^^^^^^^^^^^

The log service provides the following method:

.. autoclass:: LogService
   :members: log


Log Reader Service
^^^^^^^^^^^^^^^^^^

The log reader provides the following methods:

.. autoclass:: LogService
   :members: add_log_listener, remove_log_listener, get_log

   The result of :meth:`~LogService.get_log` and the argument to listeners
   registered with :meth:`~LogService.add_log_listener` is a :class:`LogEntry`
   object, giving read-only access to the following properties:

.. autoclass:: LogEntry
   :members: bundle, message, exception, level, osgi_level, reference, time


.. note:: ``LogEntry`` is a read-only bean which can't be un-marshalled by
   Pelix Remote Services transport providers. As a consequence, it is not
   possible to get the content of a remote log service as is.


Sample Usage
------------

Using the shell is pretty straightforward, as it can be seen in the
``pelix.shell.log`` bundle.

.. code-block:: python

   import logging

   from pelix.ipopo.decorators import ComponentFactory, Requires, Instantiate, \
      Validate, Invalidate
   from pelix.misc import LOG_SERVICE

   @ComponentFactory("log-sample-factory")
   @Requires("_logger", LOG_SERVICE)
   @Instantiate("log-sample")
   class SampleLog(object):
       """
       Provides shell commands to print the content of the log service
       """
       def __init__(self):
           self._logger = None

       @Validate
       def _validate(self, context):
           self._logger.log(logging.INFO, "Component validated")

       @Invalidate
       def _invalidate(self, context):
           self._logger.log(logging.WARNING, "Component invalidated")

In the current implementation, both services are provided by the same object,
which means that the methods of a service are accessible through the other.
This is unlikely to change, due to the simplifications it provides in the
source code.
This means that the ``_logger`` member in the snippet gives access both to the
:meth:`~LogService.log` and :meth:`~LogService.get_log` methods.

This means that the following code can be added easily to the previous snippet:

.. code-block:: python

   # [...]
   @Validate
   def _validate(self, context):
       self._logger.log(logging.INFO, "Component validated")
       self._logger.add_log_listener(self)

   def logged(self, entry):
       print("Got a log:", entry.message, "at level", entry.level)


Shell Commands
--------------

The ``pelix.shell.log`` bundle provides a set of commands in the ``log`` shell
namespace, to interact with the log services:

======== =======================================================================
Command  Description
======== =======================================================================
log      Prints the last ``N`` entries with level higher than the given one (``WARNING`` by default)
debug    Logs a message at ``DEBUG`` level
info     Logs a message at ``INFO`` level
warning  Logs a message at ``WARNING`` level
warn     An alias of the ``warning`` command
error    Logs a message at ``ERROR`` level
======== =======================================================================


.. code-block:: shell

   $ install pelix.misc.log
   Bundle ID: 12
   $ start $?
   Starting bundle 12 (pelix.misc.log)...
   $ install pelix.shell.log
   Bundle ID: 13
   $ start $?
   Starting bundle 13 (pelix.shell.log)...
   $ debug "Some debug log"
   $ info "..INFO.."
   $ warning !!WARN!!
   $ error oops
   $ log 3
   WARNING :: 2017-03-10 12:06:29.131131 :: pelix.shell.log :: !!WARN!!
    ERROR  :: 2017-03-10 12:06:31.884023 :: pelix.shell.log :: oops
   $ log info
    INFO   :: 2017-03-10 12:06:26.331350 :: pelix.shell.log :: ..INFO..
   WARNING :: 2017-03-10 12:06:29.131131 :: pelix.shell.log :: !!WARN!!
    ERROR  :: 2017-03-10 12:06:31.884023 :: pelix.shell.log :: oops
   $ log info 2
   WARNING :: 2017-03-10 12:06:29.131131 :: pelix.shell.log :: !!WARN!!
    ERROR  :: 2017-03-10 12:06:31.884023 :: pelix.shell.log :: oops
   $
