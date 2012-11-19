.. Tutorial iPOPO Manipulation

.. _manipulation:

iPOPO Manipulation
##################

This tutorial shows how iPOPO manipulation works and how to programmatically
manipulate a class.

.. _FactoryContext:

Factory Context
***************

A class is considered manipulated if it contains the factory context and the
factory context data fields, respectively ``__ipopo_factory_context__`` and
``__ipopo_factory_context_data__``.
The first field contains a ``FactoryContext`` instance while the second one
contains its dictionary form, as described in the next section.


The factory context is described in a ``pelix.ipopo.core.FactoryContext``
object or in its dictionary form. This allows to store the context in a
type-independent way: ``ipopo.decorators``, loaded using ``import``, doesn't use
the same reference to the type ``FactoryContext`` than ``ipopo.core``, loaded
by Pelix.

Here are the field of a factory context:

+-------------------+---------------------------------------------------------+
| Field             | Description                                             |
+===================+=========================================================+
| bundle_context    | The context of the Pelix Bundle defining the factory    |
|                   | (it doesn't appear in the dictionary form)              |
+-------------------+---------------------------------------------------------+
| callbacks         | A kind -> method dictionary,                            |
|                   | see :ref:`decorator_callbacks`                          |
+-------------------+---------------------------------------------------------+
| name              | The name of the component factory                       |
+-------------------+---------------------------------------------------------+
| properties        | A name -> value dictionary that contains the default    |
|                   | value of components properties                          |
+-------------------+---------------------------------------------------------+
| properties_fields | A field name -> property name dictionary, binding       |
|                   | a class field to a component property.                  |
+-------------------+---------------------------------------------------------+
| provides          | An array of tuples describing the services provided by  |
|                   | the component. The tuples are tuples, the first element |
|                   | being the list of specifications, and the second one    |
|                   | being the name of the service controller field.         |
+-------------------+---------------------------------------------------------+
| requirements      | A field name -> Requirement descriptor dictionary.      |
+-------------------+---------------------------------------------------------+


The Requirement class is also defined in ``pelix.ipopo.core``:

+-------------------+----------------------------------------------------------+
| Field             | Description                                              |
+===================+==========================================================+
| aggregate         | If True, the requirement is an array of dependencies     |
+-------------------+----------------------------------------------------------+
| optional          | If True, the requirement is optional to validate the     |
|                   | component                                                |
+-------------------+----------------------------------------------------------+
| specifications    | The list of specifications that must provide the         |
|                   | dependency                                               |
+-------------------+----------------------------------------------------------+
| filter            | The LDAP filter used to select the dependency            |
|                   | (with specifications match)                              |
+-------------------+----------------------------------------------------------+
| __original_filter | (*internal*) The additional filter given in the @Require |
|                   | decorator.                                               |
|                   | (it is the value of ``filter`` in the dictionary form)   |
+-------------------+----------------------------------------------------------+


Decorators actions
******************

@ComponentFactory
=================

This decorator applies the final steps of the manipulation, by looking for
callback methods in the class and storing the factory context in its dictionary
form for further reading by the iPOPO service.

It also cleans up the factory context by removing fields that should not
be inherited from a parent component class. Currently, it only removes the
instantiation orders.

Finally, it injects the properties getter and setter with a ``None`` value
at the class-level, as it may help the interpreter to handle the instance-level
injection.


@Requires
=========

The requirement decorator is one of the simplest, as it constructs a Requirement
object, as described in :ref:`FactoryContext`.

The decorator then stores this object in the factory context, and injects the
field in the class.


@Property
=========

Properties are handled a bit differently than requirements.
Instead of injecting a value, which would disappear at the first modification,
iPOPO uses Python *properties*, a class-level variable with a getter, a setter
and possibly a deleter, that will handle instance-level operations.

At runtime, the properties values are stored in the component context, as
described in :ref:`runtime_injection`, and calls the methods
``_ipopo_property_getter`` and ``_ipopo_property_setter``, injected at runtime.


@Provides
=========

The provided services are stored in the factory context as a tuple, containing
the list of specifications given as parameter and a service controller.

If the service controller is not None, it is injected the same way than a
property, but its handling methods are  ``_ipopo_controller_getter``
and ``_ipopo_controller_setter``, injected at runtime too.


@Instantiate
============

The list of components that must be automatically instantiated by the iPOPO
service as soon as the factory is loaded, is stored in the
``__ipopo_instances__`` field of the class.

This field is a dictionary, using the instance name as key and the given
instance properties as values.

This field is not inherited by child components.


.. _decorator_callbacks:

Callbacks (@Bind, @Unbind, @Validate, @Invalidate)
==================================================

The callback decorators are way more simple, as they just inject a field,
``_ipopo_callbacks``, in the decorated method attribute, indicating the kind
of callback that is handled.

The arity of the method is validated before the decoration, to avoid calling
back methods with an invalid number of parameters.

The ``@ComponentFactory`` decorator reads the injected field in all methods,
and stores it in the factory context.
It is not possible to register the callbacks directly in the factory context,
as the class and therefore its context doesn't exist yet when the decorator is
called.


Injected fields
===============

.. _decorators_injection:

Decorators injection
--------------------

During the iPOPO manipulation, the following fields are injected in the class:

+--------------------------------+---------------------------------------------+
| Field                          | Description                                 |
+================================+=============================================+
| __ipopo_factory_context__      | The field that will contain the             |
|                                | ``FactoryContext`` object, instantiated by  |
|                                | the iPOPO service                           |
+--------------------------------+---------------------------------------------+
| __ipopo_factory_context_data__ | Contains the dictionary form of the         |
|                                | factory context                             |
+--------------------------------+---------------------------------------------+
| __ipopo_instances__            | Contains the dictionary that represents     |
|                                | the instances that iPOPO must start as soon |
|                                | as the factory has been loaded              |
+--------------------------------+---------------------------------------------+
| _ipopo_property_getter,        | Properties handling methods, None until     |
| _ipopo_property_setter         | the runtime manipulation is done            |
+--------------------------------+---------------------------------------------+
| _ipopo_controller_getter,      | Service controller handling methods, None   |
| _ipopo_controller_setter       | until the runtime manipulation is done      |
+--------------------------------+---------------------------------------------+
| ``field``                      | All fields defined in @Requires, @Property  |
|                                | and @Provides                               |
+--------------------------------+---------------------------------------------+


Also, the methods decorated with a callback definition will have a new
attribute:

+------------------+-----------------------------------------------+
| Attribute        | Description                                   |
+==================+===============================================+
| _ipopo_callbacks | The list of callbacks handled by this method. |
|                  | It usually contains only one value.           |
+------------------+-----------------------------------------------+


.. _runtime_injection:

Runtime injection
-----------------

When iPOPO instantiates a component, it also injects some fields:

+---------------------------+-----------------------------------------------+
| Field                     | Description                                   |
+===========================+===============================================+
| _ipopo_property_getter,   | Properties handling methods, bound to the     |
| _ipopo_property_setter    | component instance                            |
+---------------------------+-----------------------------------------------+
| _ipopo_controller_getter, | Service controller handling methods, bound to |
| _ipopo_controller_setter  | the component instance                        |
+---------------------------+-----------------------------------------------+


How to manipulate an existing class
***********************************

To manipulate an existing class, you have to call the decorators
programmatically on it.

Callback decorators must be called before any other, as it works on the methods
directly, not on the class itself.
Also, as they don't take parameters, the callback decorators are called in a
way  slightly different than the others.


.. important:: To be able to work with properties and service controllers,
   the component factory must be a *new-style* class, which means it must
   inherit from ``object``.


.. code-block:: python
   :linenos:
   
   # 1. Declare the class
   class SimpleClass(object):
      def __init__(self):
          """
          The constructor
          """
          self.my_value = 5
      
      def echo(self, message):
          """
          The service method
          """
          print('-' * self.my_value + str(message))
          return message
      
      def on_stop(self):
          """
          Some cleanup method to be called when the object won't be used
          anymore.
          """
          self.echo('Stop !')
   
   # 2. Prepare the validation methods
   @Validate
   def validate(self, context):
       self.echo('Start !')
   
   # ... another way to do it
   def invalidate(self, context):
       self.on_stop()
   
   # ... inject the methods
   SimpleClass._ipopo_validate = validate
   SimpleClass._ipopo_invalidate = Invalidate(invalidate)
   
   # 3. Manipulate the class using direct calls to decorators
   Property('my_value', 'echo.value', 5)(SimpleClass)
   Provides('echo-service')(SimpleClass)
   ComponentFactory('simple-class-factory')(SimpleClass)
   
   # 4. Register the factory in iPOPO
   ipopo = pelix.ipopo.constants.get_ipopo_svc_ref(framework_bundle_context)[1]
   ipopo.register_factory(framework_bundle_context, SimpleClass)


The injection of validation methods is optional, but might be useful to clean
resources, etc.

As always, the ``ComponentFactory`` decorator must be the last to be called as
it will complete the manipulation with the final injections.
