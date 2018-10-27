#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Defines the iPOPO decorators classes to manipulate component factory classes

:author: Thomas Calmant
:copyright: Copyright 2018, Thomas Calmant
:license: Apache License 2.0
:version: 0.8.1

..

    Copyright 2018 Thomas Calmant

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

# Standard library
import inspect
import logging
import sys
import threading
import types

# Standard typing module should be optional
try:
    # pylint: disable=W0611
    from typing import Any, Callable
except ImportError:
    pass

# Pelix modules
from pelix.utilities import is_string, to_iterable, get_method_arguments
from pelix.ipopo.contexts import FactoryContext, Requirement
import pelix.ipopo.constants as constants

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Prepare the module logger
_logger = logging.getLogger("ipopo.decorators")

# ------------------------------------------------------------------------------


def is_from_parent(cls, attribute_name, value=None):
    # type: (type, str, bool) -> bool
    """
    Tests if the current attribute value is shared by a parent of the given
    class.

    Returns None if the attribute value is None.

    :param cls: Child class with the requested attribute
    :param attribute_name: Name of the attribute to be tested
    :param value: The exact value in the child class (optional)
    :return: True if the attribute value is shared with a parent class
    """
    if value is None:
        try:
            # Get the current value
            value = getattr(cls, attribute_name)
        except AttributeError:
            # No need to go further: the attribute does not exist
            return False

    for base in cls.__bases__:
        # Look for the value in each parent class
        try:
            return getattr(base, attribute_name) is value
        except AttributeError:
            pass

    # Attribute value not found in parent classes
    return False


def get_factory_context(cls):
    # type: (type) -> FactoryContext
    """
    Retrieves the factory context object associated to a factory. Creates it
    if needed

    :param cls: The factory class
    :return: The factory class context
    """
    context = getattr(cls, constants.IPOPO_FACTORY_CONTEXT, None)

    if context is None:
        # Class not yet manipulated
        context = FactoryContext()
    elif is_from_parent(cls, constants.IPOPO_FACTORY_CONTEXT):
        # Create a copy the context
        context = context.copy(True)
        # * Manipulation has not been applied yet
        context.completed = False
    else:
        # Nothing special to do
        return context

    # Context has been created or copied, inject the new bean
    setattr(cls, constants.IPOPO_FACTORY_CONTEXT, context)
    return context


def get_method_description(method):
    # type: (Callable) -> str
    """
    Retrieves a description of the given method. If possible, the description
    contains the source file name and line.

    :param method: A method
    :return: A description of the method (at least its name)
    :raise AttributeError: Given object has no __name__ attribute
    """
    try:
        try:
            line_no = inspect.getsourcelines(method)[1]
        except IOError:
            # Error reading the source file
            line_no = -1

        return "'{method}' ({file}:{line})".format(
            method=method.__name__, file=inspect.getfile(method), line=line_no
        )
    except TypeError:
        # Method can't be inspected
        return "'{0}'".format(method.__name__)


def validate_method_arity(method, *needed_args):
    # type: (Callable, *str) -> None
    """
    Tests if the decorated method has a sufficient number of parameters.

    :param method: The method to be tested
    :param needed_args: The name (for description only) of the needed
                        arguments, without "self".
    :return: Nothing
    :raise TypeError: Invalid number of parameter
    """
    nb_needed_args = len(needed_args)

    # Test the number of parameters
    arg_spec = get_method_arguments(method)
    method_args = arg_spec.args

    try:
        # Remove the self argument when present
        if method_args[0] == "self":
            del method_args[0]
    except IndexError:
        pass

    nb_args = len(method_args)

    if arg_spec.varargs is not None:
        # Variable arguments
        if nb_args != 0:
            # Other arguments detected
            raise TypeError(
                "When using '*args', the decorated {0} method must only "
                "accept the 'self' argument".format(
                    get_method_description(method)
                )
            )
    elif arg_spec.keywords is not None:
        raise TypeError("Methods using '**kwargs' are not handled")
    elif nb_args != nb_needed_args:
        # "Normal" arguments
        raise TypeError(
            "The decorated method {0} must accept exactly {1} parameters: "
            "(self, {2})".format(
                get_method_description(method),
                nb_needed_args + 1,
                ", ".join(needed_args),
            )
        )


# ------------------------------------------------------------------------------


def _ipopo_setup_callback(cls, context):
    # type: (type, FactoryContext) -> None
    """
    Sets up the class _callback dictionary

    :param cls: The class to handle
    :param context: The factory class context
    """
    assert inspect.isclass(cls)
    assert isinstance(context, FactoryContext)

    if context.callbacks is not None:
        callbacks = context.callbacks.copy()
    else:
        callbacks = {}

    functions = inspect.getmembers(cls, inspect.isroutine)

    for _, func in functions:
        if not hasattr(func, constants.IPOPO_METHOD_CALLBACKS):
            # No attribute, get the next member
            continue

        method_callbacks = getattr(func, constants.IPOPO_METHOD_CALLBACKS)
        if not isinstance(method_callbacks, list):
            # Invalid content
            _logger.warning(
                "Invalid callback information %s in %s",
                constants.IPOPO_METHOD_CALLBACKS,
                get_method_description(func),
            )
            continue

        # Keeping it allows inheritance : by removing it, only the first
        # child will see the attribute -> Don't remove it

        # Store the call backs
        for _callback in method_callbacks:
            if _callback in callbacks and not is_from_parent(
                cls, callbacks[_callback].__name__, callbacks[_callback]
            ):
                _logger.warning(
                    "Redefining the callback %s in class '%s'.\n"
                    "\tPrevious callback : %s\n"
                    "\tNew callback : %s",
                    _callback,
                    cls.__name__,
                    get_method_description(callbacks[_callback]),
                    get_method_description(func),
                )

            callbacks[_callback] = func

    # Update the factory context
    context.callbacks.clear()
    context.callbacks.update(callbacks)


def _ipopo_setup_field_callback(cls, context):
    # type: (type, FactoryContext) -> None
    """
    Sets up the class _field_callback dictionary

    :param cls: The class to handle
    :param context: The factory class context
    """
    assert inspect.isclass(cls)
    assert isinstance(context, FactoryContext)

    if context.field_callbacks is not None:
        callbacks = context.field_callbacks.copy()
    else:
        callbacks = {}

    functions = inspect.getmembers(cls, inspect.isroutine)
    for name, func in functions:
        if not hasattr(func, constants.IPOPO_METHOD_FIELD_CALLBACKS):
            # No attribute, get the next member
            continue

        method_callbacks = getattr(func, constants.IPOPO_METHOD_FIELD_CALLBACKS)
        if not isinstance(method_callbacks, list):
            # Invalid content
            _logger.warning(
                "Invalid attribute %s in %s",
                constants.IPOPO_METHOD_FIELD_CALLBACKS,
                name,
            )
            continue

        # Keeping it allows inheritance : by removing it, only the first
        # child will see the attribute -> Don't remove it

        # Store the call backs
        for kind, field, if_valid in method_callbacks:
            fields_cbs = callbacks.setdefault(field, {})

            if kind in fields_cbs and not is_from_parent(
                cls, fields_cbs[kind][0].__name__
            ):
                _logger.warning(
                    "Redefining the callback %s in '%s'. "
                    "Previous callback : '%s' (%s). "
                    "New callback : %s",
                    kind,
                    name,
                    fields_cbs[kind][0].__name__,
                    fields_cbs[kind][0],
                    func,
                )

            fields_cbs[kind] = (func, if_valid)

    # Update the factory context
    context.field_callbacks.clear()
    context.field_callbacks.update(callbacks)


# ------------------------------------------------------------------------------


def _set_object_entry(obj, entry_name, value):
    # type: (Any, str, Any) -> None
    """
    Sets the given value to the given attribute in the given object.

    :param obj: The object that contains the list
    :param entry_name: The name of the member in *obj*
    :param value: The value to set
    """
    setattr(obj, entry_name, value)


def _append_object_entry(obj, list_name, entry):
    # type: (Any, str, Any) -> None
    """
    Appends the given entry in the given object list.
    Creates the list field if needed.

    :param obj: The object that contains the list
    :param list_name: The name of the list member in *obj*
    :param entry: The entry to be added to the list
    :raise ValueError: Invalid attribute content
    """
    # Get the list
    obj_list = getattr(obj, list_name, None)
    if obj_list is None:
        # We'll have to create it
        obj_list = []
        setattr(obj, list_name, obj_list)

    assert isinstance(obj_list, list)

    # Set up the property, if needed
    if entry not in obj_list:
        obj_list.append(entry)


# ------------------------------------------------------------------------------


class Holder(object):
    # pylint: disable=R0903
    """
    Simple class that holds a value
    """

    def __init__(self, value):
        """
        Sets up the holder instance
        """
        self.value = value


def _ipopo_class_field_property(name, value, methods_prefix):
    # type: (str, Any, str) -> property
    """
    Sets up an iPOPO field property, using Python property() capabilities

    :param name: The property name
    :param value: The property default value
    :param methods_prefix: The common prefix of the getter and setter injected
                           methods
    :return: A generated Python property()
    """
    # The property lock
    lock = threading.RLock()

    # Prepare the methods names
    getter_name = "{0}{1}".format(methods_prefix, constants.IPOPO_GETTER_SUFFIX)
    setter_name = "{0}{1}".format(methods_prefix, constants.IPOPO_SETTER_SUFFIX)

    local_holder = Holder(value)

    def get_value(self):
        """
        Retrieves the property value, from the iPOPO dictionaries
        """
        getter = getattr(self, getter_name, None)
        if getter is not None:
            # Use the component getter
            with lock:
                return getter(self, name)
        else:
            # Use the local holder
            return local_holder.value

    def set_value(self, new_value):
        """
        Sets the property value and trigger an update event

        :param new_value: The new property value
        """
        setter = getattr(self, setter_name, None)
        if setter is not None:
            # Use the component setter
            with lock:
                setter(self, name, new_value)
        else:
            # Change the local holder
            local_holder.value = new_value

    return property(get_value, set_value)


# ------------------------------------------------------------------------------


class Instantiate(object):
    # pylint: disable=R0903
    """
    This decorator tells iPOPO to instantiate a component instance from this
    factory as soon as its bundle is in **ACTIVE** state.

    It accepts the following arguments:

    :param name: The name of the component instance (**mandatory**)
    :param properties: The initial properties of the instance

    If no properties are given, the default value declared in ``@Property``
    decorators will be used.

    The properties are associated to the component instance but not added to it.
    This means that new (meta-) properties can be added to add information to
    the component (like the Remote Services export properties), but those won't
    be accessible directly by the component.
    Those extra properties will be visible in component's services properties
    and in the instance properties returned by the iPOPO
    ``get_instance_details()`` method, but no new field will be injected in the
    component instance.

    .. code-block:: python

        @ComponentFactory()
        @Property('_name', 'name', 'foo')
        @Instantiate('component-1')
        @Instantiate('component-2', {'name': 'bar'})
        class Foo(object):
            pass
    """

    def __init__(self, name, properties=None):
        """
        :param name: Instance name
        :param properties: Instance properties
        """
        if not is_string(name):
            raise TypeError("Instance name must be a string")

        if properties is not None and not isinstance(properties, dict):
            raise TypeError("Instance properties must be a dictionary or None")

        name = name.strip()
        if not name:
            raise ValueError("Invalid instance name '{0}'".format(name))

        self.__name = name
        self.__properties = properties

    def __call__(self, factory_class):
        """
        Sets up and registers the instances descriptions

        :param factory_class: The factory class to instantiate
        :return: The decorated factory class
        :raise TypeError: The given object is not a class
        """
        if not inspect.isclass(factory_class):
            raise TypeError(
                "@Instantiate can decorate only classes, "
                "not '{0}'".format(type(factory_class).__name__)
            )

        # Store the instance in the factory context
        context = get_factory_context(factory_class)
        try:
            context.add_instance(self.__name, self.__properties)

        except NameError:
            _logger.warning(
                "Component '%s' defined twice, new definition ignored",
                self.__name,
            )

        return factory_class


# ------------------------------------------------------------------------------


class ComponentFactory(object):
    # pylint: disable=R0903
    """
    Manipulates the component class according to a ``FactoryContext`` object
    filled by other decorators.

    This **must** be the last executed decorator, *i.e.* the one on top of
    others in the source code.

    It accepts the following arguments:

    :param name: the name of the component factory
    :param excluded: the list of the IDs of the handlers which configuration
                     must **not** be inherited from a parent component class

    If no factory name is given, it will be generated as ``ClassNameFactory``,
    *e.g.* a ``Foo`` class will have the factory name ``FooFactory``.

    The ``__init__()`` method of a component factory must not require any
    parameter.

    .. code-block:: python

        @ComponentFactory()
        class Foo(object):
            def __init__(self):
                pass

        @ComponentFactory('my-factory')
        class Bar(object):
           pass
    """

    def __init__(self, name=None, excluded=None):
        """
        :param name: Name of the component factory
        :param excluded: List of IDs of handlers which configuration must not
                         be inherited from the parent class
        """
        self.__factory_name = name
        self.__excluded_inheritance = to_iterable(excluded)

    def __call__(self, factory_class):
        """
        Sets up and registers the factory class

        :param factory_class: The class to decorate
        :return: The decorated class
        :raise TypeError: The given object is not a class
        """
        if not inspect.isclass(factory_class):
            raise TypeError(
                "@ComponentFactory can decorate only classes, "
                "not '{0}'".format(type(factory_class).__name__)
            )

        # Get the factory context
        context = get_factory_context(factory_class)

        # Test if a manipulation has already been applied
        if not context.completed:
            # Set up the factory name
            if not self.__factory_name:
                self.__factory_name = factory_class.__name__ + "Factory"

            # Manipulate the class...

            # Update the factory context
            context.name = self.__factory_name
            context.inherit_handlers(self.__excluded_inheritance)
            context.is_singleton = False
            context.completed = True

            # Find callbacks
            _ipopo_setup_callback(factory_class, context)
            _ipopo_setup_field_callback(factory_class, context)

            # Store the factory context in its field
            setattr(factory_class, constants.IPOPO_FACTORY_CONTEXT, context)

            # Inject the properties getter and setter if needed
            if context.properties_fields:
                setattr(
                    factory_class,
                    constants.IPOPO_PROPERTY_PREFIX
                    + constants.IPOPO_GETTER_SUFFIX,
                    None,
                )
                setattr(
                    factory_class,
                    constants.IPOPO_PROPERTY_PREFIX
                    + constants.IPOPO_SETTER_SUFFIX,
                    None,
                )
        else:
            # Manipulation already applied: do nothing more
            _logger.error(
                "%s has already been manipulated with the name '%s'."
                " Keeping the old name.",
                get_method_description(factory_class),
                context.name,
            )

        return factory_class


class SingletonFactory(ComponentFactory):
    # pylint: disable=R0903
    """
    This decorator is a specialization of the :class:`~ComponentFactory`: it
    accepts the same arguments and follows the same rule, but it allows only
    one instance of component from this factory at a time.

    If the factory is instantiated while another already exist, a
    ``ValueError`` will be raised.

    .. code-block:: python

        @SingletonFactory()
        class Foo(object):
            def __init__(self):
                pass

        @SingletonFactory('my-factory')
        class Bar(object):
           pass
    """

    def __call__(self, factory_class):
        """
        Sets up and registers the factory class

        :param factory_class: The class to decorate
        :return: The decorated class
        :raise TypeError: The given object is not a class
        """
        # Manipulate the class
        factory_class = super(SingletonFactory, self).__call__(factory_class)

        # Set the singleton flag
        context = get_factory_context(factory_class)
        context.is_singleton = True
        return factory_class


# ------------------------------------------------------------------------------


class Property(object):
    # pylint: disable=R0903
    """
    The ``@Property`` decorator defines a component property. A property can
    be used to configure the component at validation time and to expose the
    state of a component.
    Note that component properties are exposed in the properties of the
    services it provides.

    This decorator accepts the following parameters:

    :param field: The property field in the class (can't be None nor empty)
    :param name: The property name (if None, this will be the field name)
    :param value: The property value (None by default)
    :Handler ID: :py:const:`pelix.ipopo.constants.HANDLER_PROPERTY`

    If no initial value is given, the value stored in the field in the
    ``__init__()`` method will be used.

    .. warning:: In Python 2, it is required that the component class inherits
                 ``object`` for properties to work.

    .. code-block:: python

        @ComponentFactory()
        @Property('_answer', 'some.answer', 42)
        class Foo(object):
            pass
    """
    HANDLER_ID = constants.HANDLER_PROPERTY
    """ ID of the handler configured by this decorator """

    def __init__(self, field, name=None, value=None):
        """
        :param field: The property field in the class (can't be None nor empty)
        :param name: The property name (if None, this will be the field name)
        :param value: The property value (None by default)
        :raise TypeError: Invalid argument type
        :raise ValueError: If the name or the name is None or empty
        """
        # Field validity test
        if not is_string(field):
            raise TypeError("Field name must be a string")

        field = field.strip()
        if not field or " " in field:
            raise ValueError(
                "Empty or invalid property field name '{0}'".format(field)
            )

        # Name validity test
        if name is not None:
            if not is_string(name):
                raise TypeError("Property name must be a string")

            name = name.strip()

        if not name:
            # No name given: use the field name
            name = field

        self._field = field
        self._name = name
        self._value = value

    def __call__(self, clazz):
        """
        Adds the property to the class iPOPO properties field.
        Creates the field if needed.

        :param clazz: The class to decorate
        :return: The decorated class
        :raise TypeError: If *clazz* is not a type
        """
        if not inspect.isclass(clazz):
            raise TypeError(
                "@Property can decorate only classes, not '{0}'".format(
                    type(clazz).__name__
                )
            )

        # Get the factory context
        context = get_factory_context(clazz)
        if context.completed:
            # Do nothing if the class has already been manipulated
            _logger.warning(
                "@Property: Already manipulated class: %s",
                get_method_description(clazz),
            )
            return clazz

        # Set up the property in the class
        context.properties[self._name] = self._value

        # Associate the field to the property name
        context.properties_fields[self._field] = self._name

        # Mark the handler in the factory context
        context.set_handler(self.HANDLER_ID, None)

        # Inject a property in the class. The property will call an instance
        # level getter / setter, injected by iPOPO after the instance creation
        setattr(
            clazz,
            self._field,
            _ipopo_class_field_property(
                self._name, self._value, constants.IPOPO_PROPERTY_PREFIX
            ),
        )

        return clazz


class HiddenProperty(Property):
    # pylint: disable=R0903
    """
    The ``@HiddenProperty`` decorator defines a component property which won't
    be visible in the properties of the services it provides.
    This kind of property is also not accessible using iPOPO reflection methods.

    This decorator accepts the same parameters and follows the same rules as
    :class:`Property`.

    .. code-block:: python

        @ComponentFactory()
        @HiddenProperty('_password', 'some.password', "secret")
        class Foo(object):
            pass
    """

    def __call__(self, clazz):
        """
        Adds the property to the class iPOPO properties field.
        Creates the field if needed.

        :param clazz: The class to decorate
        :return: The decorated class
        :raise TypeError: If *clazz* is not a type
        """
        if not inspect.isclass(clazz):
            raise TypeError(
                "@HiddenProperty can decorate only classes, not '{0}'".format(
                    type(clazz).__name__
                )
            )

        # Get the factory context
        context = get_factory_context(clazz)
        if context.completed:
            # Do nothing if the class has already been manipulated
            _logger.warning(
                "@HiddenProperty: Already manipulated class: %s",
                get_method_description(clazz),
            )
            return clazz

        # Set up the property in the class
        context.hidden_properties[self._name] = self._value

        # Mark the handler in the factory context
        context.set_handler(self.HANDLER_ID, None)

        # Inject a property in the class. The property will call an instance
        # level getter / setter, injected by iPOPO after the instance creation
        setattr(
            clazz,
            self._field,
            _ipopo_class_field_property(
                self._name, self._value, constants.IPOPO_HIDDEN_PROPERTY_PREFIX
            ),
        )

        return clazz


# ------------------------------------------------------------------------------


def _get_specifications(specifications):
    """
    Computes the list of strings corresponding to the given specifications

    :param specifications: A string, a class or a list of specifications
    :return: A list of strings
    :raise ValueError: Invalid specification found
    """
    if not specifications or specifications is object:
        raise ValueError("No specifications given")
    elif inspect.isclass(specifications):
        if Provides.USE_MODULE_QUALNAME:
            if sys.version_info < (3, 3, 0):
                raise ValueError(
                    "Qualified name capability requires Python 3.3+"
                )

            # Get the name of the class
            if not specifications.__module__:
                return [specifications.__qualname__]

            return [
                "{0}.{1}".format(
                    specifications.__module__, specifications.__qualname__
                )
            ]
        else:
            # Legacy behavior
            return [specifications.__name__]
    elif is_string(specifications):
        # Specification name
        specifications = specifications.strip()
        if not specifications:
            raise ValueError("Empty specification given")
        return [specifications]
    elif isinstance(specifications, (list, tuple)):
        # List given: normalize its content
        results = []
        for specification in specifications:
            results.extend(_get_specifications(specification))
        return results
    else:
        raise ValueError(
            "Unhandled specifications type : {0}".format(
                type(specifications).__name__
            )
        )


class Provides(object):
    # pylint: disable=R0903
    """
    The ``@Provides`` decorator defines a service to be exposed by component
    instances.
    This service will be registered (visible) in the Pelix service registry
    while the component is valid and the service controller is set to ``True``.

    This decorator accepts the following parameters:

    :param specifications: A list of provided specification(s), or the single
                           provided specification (can't be empty)
    :param controller: The name of the service controller class field
                       (optional)
    :param factory: If True, this service is a service factory
                    (optional)
    :param prototype: If True, this service is prototype service factory
                      (optional)
    :Handler ID: :py:const:`pelix.ipopo.constants.HANDLER_PROVIDES`

    All the properties of the component defined with the :class:`Property`
    decorator will be visible in the service properties.

    The controller is a Python *property* that must contain a boolean.
    By default, the controller is set to ``True``, *i.e.* the service will be
    provided by the component when it is validated.

    .. code-block:: python

        @ComponentFactory()
        # 'answer.value' will be a property of the service
        @Property('_answer', 'answer.value')
        @Provides('hello.world')
        class Foo(object):
            pass

        @ComponentFactory()
        # This service will provide multiple specifications
        @Provides(['hello.world', 'hello.world.extended'], '_svc_flag')
        class Bar(object):
            # self._svc_flag = False ; to forbid the service to be provided
            # self._svc_flag = True  ; to provide the service
            pass
    """
    HANDLER_ID = constants.HANDLER_PROVIDES
    """ ID of the handler configured by this decorator """

    USE_MODULE_QUALNAME = False
    """
    Selects the methodology to generate a specification from a class.
    A value of False uses __name__ (legacy), while True enables
    __name__ + '.' + __qualname__
    """

    def __init__(
        self, specifications, controller=None, factory=False, prototype=False
    ):
        """
        Sets up a provided service.
        A service controller can be defined to enable or disable the service.

        :param specifications: A list of provided interface(s) name(s)
                               (can't be empty)
        :param controller: Name of the service controller class field
                           (optional)
        :param factory: If True, this service is a service factory
        :param prototype: If True, this service is prototype service factory
        :raise ValueError: If the specifications are invalid
        """
        if controller is not None:
            if not is_string(controller):
                raise ValueError("Controller name must be a string")

            controller = controller.strip()
            if not controller:
                # Empty controller name
                _logger.warning("Empty controller name given")
                controller = None
            elif " " in controller:
                raise ValueError("Controller name contains spaces")

        self.__specifications = specifications
        self.__controller = controller
        self.__is_factory = factory
        self.__is_prototype = prototype

    def __call__(self, clazz):
        """
        Adds the provided service information to the class context iPOPO field.
        Creates the field if needed.

        :param clazz: The class to decorate
        :return: The decorated class
        :raise TypeError: If *clazz* is not a type or if the service factory
                          methods are missing
        """
        if not inspect.isclass(clazz):
            raise TypeError(
                "@Provides can decorate only classes, not '{0}'".format(
                    type(clazz).__name__
                )
            )

        # Get the factory context
        context = get_factory_context(clazz)
        if context.completed:
            # Do nothing if the class has already been manipulated
            _logger.warning(
                "@Provides: Already manipulated class: %s",
                get_method_description(clazz),
            )
            return clazz

        # Avoid duplicates (but keep the order)
        filtered_specs = []
        if not self.__specifications:
            filtered_specs = _get_specifications(clazz.__bases__)
        else:
            # Avoid duplicates (but keep the order)
            specs = _get_specifications(self.__specifications)
            for spec in specs:
                if spec not in filtered_specs:
                    filtered_specs.append(spec)

        # Store the service information
        config = context.set_handler_default(self.HANDLER_ID, [])
        config.append(
            (
                filtered_specs,
                self.__controller,
                self.__is_factory,
                self.__is_prototype,
            )
        )

        if self.__controller:
            # Inject a property in the class. The property will call an
            # instance level getter / setter, injected by iPOPO after the
            # instance creation
            setattr(
                clazz,
                self.__controller,
                _ipopo_class_field_property(
                    self.__controller, True, constants.IPOPO_CONTROLLER_PREFIX
                ),
            )

            # Inject the future controller methods
            setattr(
                clazz,
                constants.IPOPO_CONTROLLER_PREFIX
                + constants.IPOPO_GETTER_SUFFIX,
                None,
            )
            setattr(
                clazz,
                constants.IPOPO_CONTROLLER_PREFIX
                + constants.IPOPO_SETTER_SUFFIX,
                None,
            )

        if self.__is_factory or self.__is_prototype:
            # Ensure that the service factory methods exist
            try:
                validate_method_arity(
                    clazz.get_service, "bundle", "service_registration"
                )
                validate_method_arity(
                    clazz.unget_service, "bundle", "service_registration"
                )
            except AttributeError as ex:
                raise TypeError(
                    "Service factories must provide an {} method".format(ex)
                )

        if self.__is_prototype:
            # Ensure that the prototype service factory methods exist
            try:
                validate_method_arity(
                    clazz.unget_service_instance,
                    "bundle",
                    "service_registration",
                    "service",
                )
            except AttributeError as ex:
                raise TypeError(
                    "Prototype Service factories must provide "
                    "an {} method".format(ex)
                )

        return clazz


# ------------------------------------------------------------------------------


class Requires(object):
    # pylint: disable=R0903
    """
    The ``@Requires`` decorator defines the requirement of a service.
    It accepts the following parameters:

    :param field: The field where to inject the requirement
    :param specification: The specification of the service to inject
    :param aggregate: If True, injects a list of services, else the first
                      matching service
    :param optional: If True, this injection is optional: the component can be
                     valid without it
    :param spec_filter: An LDAP query to filter injected services according to
                        their properties
    :param immediate_rebind:
            If True, the component won't be invalidated then re-validated if a
            matching service is available when the injected dependency is
            unbound
    :Handler ID: :py:const:`pelix.ipopo.constants.HANDLER_REQUIRES`


    The ``field`` and ``specification`` attributes are mandatory.
    By default, a requirement is neither aggregated nor optional (both are set
    to ``False`` and no specification filter is used.

    .. note:: Since iPOPO 0.5.4, only one specification can be given.

    .. code-block:: python

        @ComponentFactory()
        @Requires('_hello', 'hello.world')
        class Foo(object):
            pass

        @ComponentFactory()
        @Requires('_hello', 'hello.world', aggregate=True, optional=False,
                  spec_filter='(language=fr)')
        class Bar(object):
            pass
    """
    HANDLER_ID = constants.HANDLER_REQUIRES
    """ ID of the handler configured by this decorator """

    def __init__(
        self,
        field,
        specification,
        aggregate=False,
        optional=False,
        spec_filter=None,
        immediate_rebind=False,
    ):
        """
        :param field: The injected field
        :param specification: The injected service specification
        :param aggregate: If True, injects a list
        :param optional: If True, this injection is optional
        :param spec_filter: An LDAP query to filter injected services upon
                            their properties
        :param immediate_rebind:
            If True, the component won't be invalidated then re-validated if a
            matching service is available when the injected dependency is
            unbound
        :raise TypeError: A parameter has an invalid type
        :raise ValueError: An error occurred while parsing the filter or an
                           argument is incorrect
        """
        if not field:
            raise ValueError("Empty field name.")

        if not is_string(field):
            raise TypeError(
                "The field name must be a string, not {0}".format(
                    type(field).__name__
                )
            )

        if " " in field:
            raise ValueError("Field name can't contain spaces.")

        self._field = field

        # Be sure that there is only one required specification
        specifications = _get_specifications(specification)
        self._multi_specs = len(specifications) > 1

        # Construct the requirement object
        self._requirement = Requirement(
            specifications[0],
            aggregate,
            optional,
            spec_filter,
            immediate_rebind,
        )

    def __call__(self, clazz):
        """
        Adds the requirement to the class iPOPO field

        :param clazz: The class to decorate
        :return: The decorated class
        :raise TypeError: If *clazz* is not a type
        """
        if not inspect.isclass(clazz):
            raise TypeError(
                "@{0} can decorate only classes, not '{1}'".format(
                    type(self).__name__, type(clazz).__name__
                )
            )

        if self._multi_specs:
            _logger.warning(
                "%s: Only one specification can be required: %s -> %s",
                type(self).__name__,
                clazz.__name__,
                self._field,
            )

        # Set up the property in the class
        context = get_factory_context(clazz)
        if context.completed:
            # Do nothing if the class has already been manipulated
            _logger.warning(
                "@%s: Already manipulated class: %s",
                type(self).__name__,
                get_method_description(clazz),
            )
            return clazz

        # Store the requirement information
        config = context.set_handler_default(self.HANDLER_ID, {})
        config[self._field] = self._requirement

        # Inject the field
        setattr(clazz, self._field, None)
        return clazz


# ------------------------------------------------------------------------------


class RequiresVarFilter(Requires):
    # pylint: disable=R0903
    """
    The ``@RequiresVarFilter`` decorator acts like :class:`Requires`, but its
    LDAP filter dynamically adapts to the properties of this component.

    :Handler ID:
            :py:const:`pelix.ipopo.constants.HANDLER_REQUIRES_VARIABLE_FILTER`

    .. code-block:: python

        @ComponentFactory()
        @Property('_lang', 'lang', 'fr')
        @RequiresVarFilter('_hello', 'hello.world', optional=True,
                           spec_filter='(language={lang})')
        class Bar(object):
            pass
    """
    HANDLER_ID = constants.HANDLER_REQUIRES_VARIABLE_FILTER
    """ ID of the handler configured by this decorator """


# ------------------------------------------------------------------------------


class RequiresBest(Requires):
    # pylint: disable=R0903
    """
    The ``@RequiresBest`` decorator acts like :class:`Requires`, but it
    always injects the service with the best rank (``service.ranking``
    property).

    Unlike most of the other requirement decorators, ``@RequiresBest`` doesn't
    support the injection of a list of services: only the best service can be
    injected.

    :Handler ID: :py:const:`pelix.ipopo.constants.HANDLER_REQUIRES_BEST`

    .. code-block:: python

        @ComponentFactory()
        @RequiresBest('_hello', 'hello.world')
        class Foo(object):
            pass

        @ComponentFactory()
        @RequiresBest('_hello', 'hello.world', optional=True,
                      spec_filter='(language=fr)')
        class Bar(object):
            pass
    """
    HANDLER_ID = constants.HANDLER_REQUIRES_BEST
    """ ID of the handler configured by this decorator """

    def __init__(
        self,
        field,
        specification,
        optional=False,
        spec_filter=None,
        immediate_rebind=True,
    ):
        """
        :param field: The injected field
        :param specification: The injected service specification
        :param optional: If true, this injection is optional
        :param spec_filter: An LDAP query to filter injected services upon
                            their properties
        :param immediate_rebind: If True, the component won't be invalidated
                                 then re-validated if a matching service is
                                 available when the injected dependency is
                                 unbound
        :raise TypeError: A parameter has an invalid type
        :raise ValueError: An error occurred while parsing the filter or an
                           argument is incorrect
        """
        super(RequiresBest, self).__init__(
            field, specification, False, optional, spec_filter, immediate_rebind
        )


# ------------------------------------------------------------------------------


class RequiresMap(Requires):
    # pylint: disable=R0903
    """
    The ``@RequiresMap`` decorator defines a requirement that must be injected
    in a dictionary.

    In addition to the arguments of :class:Requires, this decorator also accepts
    or redefines the following ones:

    :param key: The name of the service property to use as a dictionary key
    :param allow_none: If True, also injects services with the property value
                       set to None or missing
    :param aggregate: If true, injects a list of services with the same
                      property value, else injects only one service per value
    :Handler ID: :py:const:`pelix.ipopo.constants.HANDLER_REQUIRES_MAP`

    .. code-block:: python

        @ComponentFactory()
        @RequiresMap('_hello', 'hello.world', 'language')
        class Bar(object):
            # self._hello['fr'].hello('le monde')
            pass
    """
    HANDLER_ID = constants.HANDLER_REQUIRES_MAP
    """ ID of the handler configured by this decorator """

    def __init__(
        self,
        field,
        specification,
        key,
        allow_none=False,
        aggregate=False,
        optional=False,
        spec_filter=None,
    ):
        """
        :param field: The injected field
        :param specification: The injected service specification
        :param key: Name of the service property to use as a dictionary key
        :param allow_none: If True, inject services with a None property value
        :param aggregate: If true, injects a list
        :param optional: If true, this injection is optional
        :param spec_filter: An LDAP query to filter injected services upon
                            their properties
        :raise TypeError: A parameter has an invalid type
        :raise ValueError: An error occurred while parsing the filter or an
                           argument is incorrect
        """
        super(RequiresMap, self).__init__(
            field, specification, aggregate, optional, spec_filter, False
        )
        # Check if key is valid
        if not key:
            raise ValueError("No property key given")

        # Store the flags
        self._key = key
        self._allow_none = allow_none

    def __call__(self, clazz):
        """
        Adds the requirement to the class iPOPO field

        :param clazz: The class to decorate
        :return: The decorated class
        :raise TypeError: If *clazz* is not a type
        """
        clazz = super(RequiresMap, self).__call__(clazz)

        # Set up the property in the class
        context = get_factory_context(clazz)
        if not context.completed:
            # Store the requirement information
            config = context.set_handler_default(self.HANDLER_ID, {})
            config[self._field] = (
                self._requirement,
                self._key,
                self._allow_none,
            )
        return clazz


# ------------------------------------------------------------------------------


class Temporal(Requires):
    # pylint: disable=R0903
    """
    The ``@Temporal`` decorator defines a single immediate rebind requirement
    with a grace time when the injected service disappears.

    This decorator acts like :class:Requires except it doesn't support
    ``immediate_rebind`` (set to ``True``) nor ``aggregate``.
    It also adds the following argument:

    :param timeout: Temporal timeout, in seconds (must be greater than 0)
    :Handler ID: :py:const:`pelix.ipopo.constants.HANDLER_TEMPORAL`

    When the injected service disappears, the component won't be invalidated
    before the given timeout.
    If a matching is found, it is injected in-place and the component instance
    continues its operations.
    If the service is used while no service is available, the call is put in
    hold and blocks until a new service is injected or until the timeout is
    reached. In the latter case, a ``TemporalException`` is raised.

    .. code-block:: python

        @ComponentFactory()
        @Temporal('_hello', 'hello.world', timeout=5)
        class Bar(object):
            pass
    """
    HANDLER_ID = constants.HANDLER_TEMPORAL
    """ ID of the handler configured by this decorator """

    def __init__(
        self, field, specification, optional=False, spec_filter=None, timeout=10
    ):
        """
        :param field: The injected field
        :param specification: The injected service specification
        :param optional: If true, this injection is optional
        :param spec_filter: An LDAP query to filter injected services upon
                            their properties
        :param timeout: Temporal timeout, in seconds (must be greater than 0)
        :raise TypeError: A parameter has an invalid type
        :raise ValueError: An error occurred while parsing the filter or an
                           argument is incorrect
        """
        super(Temporal, self).__init__(
            field, specification, False, optional, spec_filter, True
        )
        if timeout <= 0:
            _logger.warning(
                "@Temporal timeout must be greater than 0. "
                "Using default value."
            )
            self._timeout = 10
        else:
            self._timeout = timeout

    def __call__(self, clazz):
        """
        Adds the requirement to the class iPOPO field

        :param clazz: The class to decorate
        :return: The decorated class
        :raise TypeError: If *clazz* is not a type
        """
        clazz = super(Temporal, self).__call__(clazz)

        # Store the requirement information
        context = get_factory_context(clazz)
        if not context.completed:
            config = context.set_handler_default(self.HANDLER_ID, {})
            config[self._field] = (self._requirement, self._timeout)
        return clazz


# ------------------------------------------------------------------------------


class BindField(object):
    # pylint: disable=R0903
    """
    The ``@BindField`` callback decorator is called when a component is bound
    to a dependency, injected in the given field.

    This decorator accepts the following arguments:

    :param field: The field associated to the binding
    :param if_valid: If True, call the decorated method only when the component
                     is valid

    The decorated method must accept the field where the service has been
    injected, the service object and its
    :class:`~pelix.framework.ServiceReference` as arguments::

       @BindField('_hello')
       def bind_method(self, field, service, service_reference):
           '''
           field: Field wherein the dependency is injected
           service: The injected service instance.
           service_reference: The injected service ServiceReference
           '''
           # ...

    If the service is a required one, the bind callback is called **before**
    the component is validated.
    The bind field callback is called **after** the global bind method.

    The service reference can be stored *if it is released on unbind*.

    Exceptions raised by a bind callback are ignored.
    """

    def __init__(self, field, if_valid=False):
        """
        :param field: Field associated to the binding
        :param if_valid: Call the method only if the component is valid
        """
        self._field = field
        self._if_valid = if_valid

    def __call__(self, method):
        """
        Updates the "field callback" list for this method

        :param method: Method to decorate
        :return: Decorated method
        :raise TypeError: The decorated element is not a valid function
        """
        if not inspect.isroutine(method):
            raise TypeError("@BindField can only be applied on functions")

        # Tests the number of parameters
        validate_method_arity(method, "field", "service", "service_reference")

        _append_object_entry(
            method,
            constants.IPOPO_METHOD_FIELD_CALLBACKS,
            (constants.IPOPO_CALLBACK_BIND_FIELD, self._field, self._if_valid),
        )
        return method


class UpdateField(object):
    # pylint: disable=R0903
    """
    The ``@UpdateField`` callback decorator is called when the properties of
    a service injected in the given field have been updated.

    This decorator accepts the following arguments:

    :param field: The field associated to the binding
    :param if_valid: If True, call the decorated method only when the component
                     is valid

    The decorated method must accept the field where the service has been
    injected, the service object, its
    :class:`~pelix.framework.ServiceReference` and its previous properties as
    arguments::

       @UpdateField('_hello')
       def update_method(self, service, service_reference, old_properties):
           '''
           field: Field wherein the dependency is injected
           service: The injected service instance.
           service_reference: The injected service ServiceReference
           old_properties: The previous service properties
           '''
           # ...

    Exceptions raised by an update callback are ignored.
    """

    def __init__(self, field, if_valid=False):
        """
        :param field: Field associated to the binding
        :param if_valid: Call the method only if the component is valid
        """
        self._field = field
        self._if_valid = if_valid

    def __call__(self, method):
        """
        Updates the "field callback" list for this method

        :param method: Method to decorate
        :return: Decorated method
        :raise TypeError: The decorated element is not a valid function
        """
        if not inspect.isroutine(method):
            raise TypeError("@UnbindField can only be applied on functions")

        # Tests the number of parameters
        validate_method_arity(
            method, "field", "service", "service_reference", "old_properties"
        )

        _append_object_entry(
            method,
            constants.IPOPO_METHOD_FIELD_CALLBACKS,
            (
                constants.IPOPO_CALLBACK_UPDATE_FIELD,
                self._field,
                self._if_valid,
            ),
        )
        return method


class UnbindField(object):
    # pylint: disable=R0903
    """
    The ``@UnbindField`` callback decorator is called when an injected
    dependency is unbound.

    This decorator accepts the following arguments:

    :param field: The field associated to the binding
    :param if_valid: If True, call the decorated method only when the component
                     is valid

    The decorated method must accept the field where the service has been
    injected, the service object, its
    :class:`~pelix.framework.ServiceReference` and its previous properties as
    arguments::

       @UnbindField('_hello')
       def unbind_method(self, field, service, service_reference):
           '''
           field: Field wherein the dependency was injected
           service: The injected service instance.
           service_reference: The injected service ServiceReference
           '''
           # ...

    If the service is a required one, the unbind callback is called **after**
    the component has been invalidated.
    The unbind field callback is called **before** the global unbind method.

    Exceptions raised by an unbind callback are ignored.
    """

    def __init__(self, field, if_valid=False):
        """
        :param field: Field associated to the binding
        :param if_valid: Call the method only if the component is valid
        """
        self._field = field
        self._if_valid = if_valid

    def __call__(self, method):
        """
        Updates the "field callback" list for this method

        :param method: Method to decorate
        :return: Decorated method
        :raise TypeError: The decorated element is not a valid function
        """
        if not inspect.isroutine(method):
            raise TypeError("@UnbindField can only be applied on functions")

        # Tests the number of parameters
        validate_method_arity(method, "field", "service", "service_reference")

        _append_object_entry(
            method,
            constants.IPOPO_METHOD_FIELD_CALLBACKS,
            (
                constants.IPOPO_CALLBACK_UNBIND_FIELD,
                self._field,
                self._if_valid,
            ),
        )
        return method


# ------------------------------------------------------------------------------


def Bind(method):
    # pylint: disable=C0103
    """
    The ``@Bind`` callback decorator is called when a component is bound to a
    dependency.

    The decorated method must accept the injected service object and its
    :class:`~pelix.framework.ServiceReference` as arguments::

       @Bind
       def bind_method(self, service, service_reference):
           '''
           service: The injected service instance.
           service_reference: The injected service ServiceReference
           '''
           # ...

    If the service is a required one, the bind callback is called **before**
    the component is validated.

    The service reference can be stored *if it is released on unbind*.

    Exceptions raised by a bind callback are ignored.

    :param method: The decorated method
    :raise TypeError: The decorated element is not a valid function
    """
    if not inspect.isroutine(method):
        raise TypeError("@Bind can only be applied on functions")

    # Tests the number of parameters
    validate_method_arity(method, "service", "service_reference")

    _append_object_entry(
        method, constants.IPOPO_METHOD_CALLBACKS, constants.IPOPO_CALLBACK_BIND
    )
    return method


def Update(method):
    # pylint: disable=C0103
    """
    The ``@Update`` callback decorator is called when the properties of an
    injected service have been modified.

    The decorated method must accept the injected service object and its
    :class:`~pelix.framework.ServiceReference` and the previous properties
    as arguments::

       @Update
       def update_method(self, service, service_reference, old_properties):
           '''
           service: The injected service instance.
           service_reference: The injected service ServiceReference
           old_properties: The previous service properties
           '''
           # ...

    Exceptions raised by an update callback are ignored.

    :param method: The decorated method
    :raise TypeError: The decorated element is not a valid function
    """
    if not isinstance(method, types.FunctionType):
        raise TypeError("@Update can only be applied on functions")

    # Tests the number of parameters
    validate_method_arity(
        method, "service", "service_reference", "old_properties"
    )

    _append_object_entry(
        method,
        constants.IPOPO_METHOD_CALLBACKS,
        constants.IPOPO_CALLBACK_UPDATE,
    )
    return method


def Unbind(method):
    # pylint: disable=C0103
    """
    The ``@Unbind`` callback decorator is called when a component dependency is
    unbound.

    The decorated method must accept the injected service object and its
    :class:`~pelix.framework.ServiceReference` as arguments::

       @Unbind
       def unbind_method(self, service, service_reference):
           '''
           service: The previously injected service instance.
           service_reference: Its ServiceReference
           '''
           # ...

    If the service is a required one, the unbind callback is called **after**
    the component has been invalidated.

    Exceptions raised by an unbind callback are ignored.

    :param method: The decorated method
    :raise TypeError: The decorated element is not a valid function
    """
    if not isinstance(method, types.FunctionType):
        raise TypeError("@Unbind can only be applied on functions")

    # Tests the number of parameters
    validate_method_arity(method, "service", "service_reference")

    _append_object_entry(
        method,
        constants.IPOPO_METHOD_CALLBACKS,
        constants.IPOPO_CALLBACK_UNBIND,
    )
    return method


# ------------------------------------------------------------------------------


class ValidateComponent(object):
    # pylint: disable=R0903
    """
    The ``@ValidateComponent`` decorator declares a callback method for
    component validation.

    Currently, the arguments given to the callback are read-only, to avoid
    messing with the validation life-cycle.
    In the future, it will be possible to modify the properties and to use
    the component context in order to customize the component early.

    The decorator accepts an ordered list of arguments. They define the
    signature of the decorated method.

    The arguments can be the following ones, declared in the
    ``pelix.ipopo.constants`` module:

    * ``ARG_BUNDLE_CONTEXT``: Gives access to the bundle context
    * ``ARG_COMPONENT_CONTEXT``: Gives access to the component context
    * ``ARG_PROPERTIES``: Gives access to component properties (``dict``)

    Here are some sample uses of the decorator. Note that the number and order
    of arguments only has to match the list given to the decorator::

        from pelix.constants import ARG_COMPONENT_CONTEXT, ARG_BUNDLE_CONTEXT, \
            ARG_PROPERTIES

        @ValidateComponent(ARG_COMPONENT_CONTEXT)
        def validate_component(self, component_ctx):
            # ...

        @ValidateComponent(ARG_BUNDLE_CONTEXT, ARG_COMPONENT_CONTEXT)
        def validate_component(self, bundle_ctx, component_ctx):
            # ...

        @ValidateComponent(ARG_BUNDLE_CONTEXT, ARG_COMPONENT_CONTEXT,
                           ARG_PROPERTIES)
        def validate_component(self, bundle_ctx, component_ctx, props):
            # ...
    """

    def __init__(self, *args):
        """
        :param args: An ordered list of argument descriptors.
        :raise TypeError: A parameter has an invalid type or the decorated
                          object is not a method
        """
        # Check arguments validity
        valid_args = (
            constants.ARG_BUNDLE_CONTEXT,
            constants.ARG_COMPONENT_CONTEXT,
            constants.ARG_PROPERTIES,
        )

        for arg in args:
            if arg not in valid_args:
                raise TypeError("Unknown argument type: {}".format(arg))

        # Keep track of the arguments
        self._args = tuple(args)

    def __call__(self, method):
        """
        Registers the decorated method as a callback for component validation

        :param method: The validation method
        :raise TypeError: The decorated element is not a valid function
        """
        if not isinstance(method, types.FunctionType):
            raise TypeError(
                "@ValidateComponent can only be applied on functions"
            )

        # Tests the number of parameters
        validate_method_arity(method, *self._args)

        # Append the callback to the component
        _append_object_entry(
            method,
            constants.IPOPO_METHOD_CALLBACKS,
            constants.IPOPO_CALLBACK_VALIDATE,
        )

        # Append arguments list to the method
        _set_object_entry(method, constants.IPOPO_VALIDATE_ARGS, self._args)

        return method


class InvalidateComponent(ValidateComponent):
    # pylint: disable=R0903
    """
    The ``@InvalidateComponent`` decorator declares a callback method for
    component invalidation.

    Its arguments and their order describes the ones of the callback it
    decorates.
    They are the same as those of :class:`ValidateComponent`.

    Exceptions raised by an invalidation callback are ignored.

    If the component provides a service, the invalidation method is called
    after the provided service has been unregistered to the framework.
    """

    def __call__(self, method):
        """
        Registers the decorated method as a callback for component invalidation

        :param method: The invalidation method
        :raise TypeError: The decorated element is not a valid function
        """
        if not isinstance(method, types.FunctionType):
            raise TypeError(
                "@InvalidateComponent can only be applied on functions"
            )

        # Tests the number of parameters
        validate_method_arity(method, *self._args)

        # Append the callback to the component
        _append_object_entry(
            method,
            constants.IPOPO_METHOD_CALLBACKS,
            constants.IPOPO_CALLBACK_INVALIDATE,
        )

        # Append arguments list to the method
        _set_object_entry(method, constants.IPOPO_VALIDATE_ARGS, self._args)

        return method


# ------------------------------------------------------------------------------


def Validate(method):
    # pylint: disable=C0103
    """
    The validation callback decorator is called when a component becomes valid,
    *i.e.* if all of its required dependencies has been injected.

    This is an alias to :class:`ValidateComponent`. It is not possible to have
    both ``@Validate`` and ``@ValidateComponent`` decorators used in the same
    class.

    The decorated method must accept the bundle's
    :class:`~pelix.framework.BundleContext` as argument::

       @Validate
       def validation_method(self, bundle_context):
           '''
           bundle_context: The component's bundle context
           '''
           # ...

    If the validation callback raises an exception, the component goes into
    **ERRONEOUS** state.

    If the component provides a service, the validation method is called before
    the provided service is registered to the framework.

    :param method: The validation method
    :raise TypeError: The decorated element is not a valid function
    """
    return ValidateComponent(constants.ARG_BUNDLE_CONTEXT)(method)


def Invalidate(method):
    # pylint: disable=C0103
    """
    The invalidation callback decorator is called when a component becomes
    invalid, *i.e.* if one of its required dependencies disappeared.

    This is an alias to :class:`InvalidateComponent`. It is not possible to
    have both ``@Invalidate`` and ``@InvalidateComponent`` decorators used in
    the same class.

    The decorated method must accept the bundle's
    :class:`~pelix.framework.BundleContext` as argument::

       @Invalidate
       def invalidation_method(self, bundle_context):
           '''
           bundle_context: The component's bundle context
           '''
           # ...

    Exceptions raised by an invalidation callback are ignored.

    If the component provides a service, the invalidation method is called
    after the provided service has been unregistered to the framework.

    :param method: The decorated method
    :raise TypeError: The decorated element is not a function
    """
    return InvalidateComponent(constants.ARG_BUNDLE_CONTEXT)(method)


def PostRegistration(method):
    # pylint: disable=C0103
    """
    The service post-registration callback decorator is called after a service
    of the component has been registered to the framework.

    The decorated method must accept the
    :class:`~pelix.framework.ServiceReference` of the registered
    service as argument::

       @PostRegistration
       def callback_method(self, service_reference):
           '''
           service_reference: The ServiceReference of the provided service
           '''
           # ...

    :param method: The decorated method
    :raise TypeError: The decorated element is not a valid function
    """
    if not isinstance(method, types.FunctionType):
        raise TypeError("@PostRegistration can only be applied on functions")

    # Tests the number of parameters
    validate_method_arity(method, "service_reference")
    _append_object_entry(
        method,
        constants.IPOPO_METHOD_CALLBACKS,
        constants.IPOPO_CALLBACK_POST_REGISTRATION,
    )
    return method


def PostUnregistration(method):
    # pylint: disable=C0103
    """
    The service post-unregistration callback decorator is called after a service
    of the component has been unregistered from the framework.

    The decorated method must accept the
    :class:`~pelix.framework.ServiceReference` of the registered
    service as argument::

       @PostUnregistration
       def callback_method(self, service_reference):
           '''
           service_reference: The ServiceReference of the provided service
           '''
           # ...

    :param method: The decorated method
    :raise TypeError: The decorated element is not a valid function
    """
    if not isinstance(method, types.FunctionType):
        raise TypeError("@PostUnregistration can only be applied on functions")

    # Tests the number of parameters
    validate_method_arity(method, "service_reference")
    _append_object_entry(
        method,
        constants.IPOPO_METHOD_CALLBACKS,
        constants.IPOPO_CALLBACK_POST_UNREGISTRATION,
    )
    return method
