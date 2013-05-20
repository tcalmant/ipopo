.. EventAdmin tutorial

.. _eventadmin:

EventAdmin tutorial
###################

Description
***********


Usage
*****

Instantiation
=============

* ``pelix.services.eventadmin``
* ``pelix-services-eventadmin-factory``

Configuration
=============

+--------------+---------------+-----------------------------------------------+
| Property     | Default value | Description                                   |
+==============+===============+===============================================+
| pool.threads | 10            | Number of threads in the dispatch thread poll |
+--------------+---------------+-----------------------------------------------+

Interface
=========

EventAdmin service
------------------

The EventAdmin service provides the following interface:

+-------------------------+-------------+
| Method                  | Description |
+=========================+=============+
| post(topic, properties) |             |
+-------------------------+-------------+
| send(topic, properties) |             |
+-------------------------+-------------+


EventHandler service
--------------------

The EventHandler implementations must provide the following method:

+---------------------------------+-------------+
| Method                          | Description |
+=================================+=============+
| handle_event(topic, properties) |             |
+---------------------------------+-------------+


Shell Commands
**************

``pelix.shell.eventadmin``

+---------------------------------------+------------------------------------+
| Command                               | Description                        |
+=======================================+====================================+
| post <topic> [<property=value> [...]] | Posts an event on the given topic, |
|                                       | with the given properties          |
+---------------------------------------+------------------------------------+
| send <topic> [<property=value> [...]] | Sends an event on the given topic, |
|                                       | with the given properties          |
+---------------------------------------+------------------------------------+
