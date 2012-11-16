#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Defines the iPOPO decorators classes to manipulate component factory classes

:author: Thomas Calmant
:copyright: Copyright 2012, isandlaTech
:license: GPLv3
:version: 0.4
:status: Alpha

..

    This file is part of iPOPO.

    iPOPO is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    
    iPOPO is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
    
    You should have received a copy of the GNU General Public License
    along with iPOPO. If not, see <http://www.gnu.org/licenses/>.
"""

__version__ = (0, 4, 0)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

from pelix.utilities import is_string
from pelix.ipopo.core import FactoryContext, Requirement

import pelix.ipopo.constants as constants

# ------------------------------------------------------------------------------

import inspect
import logging
import threading
import types

# ------------------------------------------------------------------------------

# Prepare the module logger
_logger = logging.getLogger("ipopo.decorators")

# ------------------------------------------------------------------------------

def is_from_parent(cls, attribute_name):
    """
    Tests if the current attribute value is shared by a parent of the given
    class.
    
    Returns None if the attribute value is None.
    
    :param cls: Child class with the requested attribute
    :param attribute_name: Name of the attribute to be tested
    :return: True if the attribute value is shared with a parent class
    """
    value = getattr(cls, attribute_name, None)
    if value is None:
        # No need to go further
        return False

    for base in cls.__bases__:
        base_value = getattr(base, attribute_name, None)
        if base_value is value:
            # Found !
            return True

    # Attribute value not found in parent classes
    return False


def get_method_description(method):
    """
    Retrieves a description of the given method. If possible, the description
    contains the source file name and line.
    
    :param method: A method
    :return: A description of the method (at least its name)
    """
    try:
        try:
            line_no = inspect.getsourcelines(method)[1]

        except IOError:
            # Error reading the source file
            line_no = -1

        return "'{method}' ({file}:{line})".format(method=method.__name__,
                                                   file=inspect.getfile(method),
                                                   line=line_no)

    except TypeError:
        # Method can't be inspected
        return "'{0}'".format(method.__name__)


def validate_method_arity(method, *needed_args):
    """
    Tests if the decorated method has a sufficient number of parameters.
    
    :param method: The method to be tested
    :param needed_args: The name (for description only) of the needed arguments,
                        without "self".
    :return: Nothing
    :raise TypeError: Invalid number of parameter
    """
    nb_needed_args = len(needed_args) + 1

    # Test the number of parameters
    argspec = inspect.getargspec(method)
    method_args = argspec.args

    if len(method_args) == 0:
        # No argument at all
        raise TypeError("Decorated method {0} must have at least the 'self' "
                        "parameter".format(get_method_description(method)))

    if argspec.varargs is not None:
        # Variable arguments
        if len(method_args) != 1 or method_args[0] != "self":
            # Other arguments detected
            raise TypeError("When using '*args', the decorated {0} method must "
                            "only accept the 'self' argument".format(
                                get_method_description(method)))

    elif len(method_args) != nb_needed_args or method_args[0] != 'self':
        # "Normal" arguments
        raise TypeError("The decorated method {0} must accept exactly {1} "
                        "parameters : (self, {2})".format(
                                get_method_description(method), nb_needed_args,
                                ", ".join(needed_args)))

# ------------------------------------------------------------------------------

def _get_factory_context(cls):
    """
    Retrieves the factory context object associated to a factory. Creates it
    if needed
    
    :param cls: The factory class
    :return: The factory class context
    """
    context = getattr(cls, constants.IPOPO_FACTORY_CONTEXT_DATA, None)

    if context is None:
        # Class not yet manipulated
        context = FactoryContext()

    else:
        if is_from_parent(cls, constants.IPOPO_FACTORY_CONTEXT_DATA):
            # The context comes from a parent, copy it using a temporary
            # dictionary form
            if isinstance(context, dict):
                context = FactoryContext.from_dictionary_form(context)

            context = context.copy()

            # Clear the values that must not be inherited:
            # * Provided services
            del context.provides[:]

        # We have a context of our own, make sure we have a FactoryContext
        if isinstance(context, dict):
            # Already manipulated and stored class
            context = FactoryContext.from_dictionary_form(context)

    setattr(cls, constants.IPOPO_FACTORY_CONTEXT_DATA, context)
    return context


def _ipopo_setup_callback(cls, context):
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

    for name, function in functions:

        if not hasattr(function, constants.IPOPO_METHOD_CALLBACKS):
            # No attribute, get the next member
            continue

        method_callbacks = getattr(function, constants.IPOPO_METHOD_CALLBACKS)

        if not isinstance(method_callbacks, list):
            # Invalid content
            _logger.warning("Invalid attribute %s in %s", \
                            constants.IPOPO_METHOD_CALLBACKS, name)
            continue

        # Keeping it allows inheritance : by removing it, only the first
        # child will see the attribute -> Don't remove it

        # Store the call backs
        for _callback in method_callbacks:
            if _callback in callbacks and \
            not is_from_parent(cls, callbacks[_callback].__name__):
                _logger.warning("Redefining the callback %s in '%s'. " \
                                "Previous callback : '%s' (%s). " \
                                "New callback : %s", _callback, name,
                                callbacks[_callback].__name__,
                                callbacks[_callback], function)

            callbacks[_callback] = function

    # Update the factory context
    context.callbacks.clear()
    context.callbacks.update(callbacks)

# ------------------------------------------------------------------------------

def _append_object_entry(obj, list_name, entry):
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
    """
    Simple class that holds a value
    """
    def __init__(self, value):
        """
        Sets up the holder instance
        """
        self.value = value


def _ipopo_class_field_property(name, value, methods_prefix):
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

class Instantiate:
    """
    Decorator that sets up a future instance of a component
    """
    def __init__(self, name, properties=None):
        """
        Sets up the decorator
        
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
            raise TypeError("@ComponentFactory can decorate only classes, " \
                            "not '{0}'".format(type(factory_class).__name__))

        instances = getattr(factory_class, constants.IPOPO_INSTANCES, None)

        if instances is None or \
            is_from_parent(factory_class, constants.IPOPO_INSTANCES):
            # No instances for this particular class
            instances = {}
            setattr(factory_class, constants.IPOPO_INSTANCES, instances)

        if self.__name not in instances:
            instances[self.__name] = self.__properties

        else:
            _logger.warn("Component '%s' defined twice, new definition ignored",
                         self.__name)

        return factory_class

# ------------------------------------------------------------------------------

class ComponentFactory:
    """
    Decorator that sets up a component factory class
    """

    # Non inheritable fields, to clean up during manipulation if needed
    NON_INHERITABLE_FIELDS = (constants.IPOPO_INSTANCES,)

    def __init__(self, name=None):
        """
        Sets up the decorator

        :param name: Name of the component factory
        """
        self.__factory_name = name


    def __call__(self, factory_class):
        """
        Sets up and registers the factory class

        :param factory_class: The class to decorate
        :return: The decorated class
        :raise TypeError: The given object is not a class
        """
        if not inspect.isclass(factory_class):
            raise TypeError("@ComponentFactory can decorate only classes, " \
                            "not '{0}'".format(type(factory_class).__name__))

        # Get the factory context
        context = _get_factory_context(factory_class)

        # Set the factory name
        if not self.__factory_name:
            self.__factory_name = factory_class.__name__ + "Factory"

        context.name = self.__factory_name

        # Find callbacks
        _ipopo_setup_callback(factory_class, context)

        # Clean up inherited fields, to avoid weird behavior
        for field in ComponentFactory.NON_INHERITABLE_FIELDS:
            if is_from_parent(factory_class, field):
                # Set inherited fields to None
                setattr(factory_class, field, None)

        # Add the factory context field (set it to None)
        setattr(factory_class, constants.IPOPO_FACTORY_CONTEXT, None)

        # Store a dictionary form of the factory context in the class
        # -> Avoids "class version" problems
        setattr(factory_class, constants.IPOPO_FACTORY_CONTEXT_DATA, \
                context.to_dictionary_form())

        # Inject the properties getter and setter if needed
        if len(context.properties_fields) > 0:
            setattr(factory_class, constants.IPOPO_PROPERTY_PREFIX \
                    + constants.IPOPO_GETTER_SUFFIX, None)
            setattr(factory_class, constants.IPOPO_PROPERTY_PREFIX \
                    + constants.IPOPO_SETTER_SUFFIX, None)

        return factory_class

# ------------------------------------------------------------------------------

class Property:
    """
    @Property decorator
    
    Defines a component property.
    """
    def __init__(self, field=None, name=None, value=None):
        """
        Sets up the property
        
        :param field: The property field in the class (can't be None nor empty)
        :param name: The property name (if None, this will be the field name)
        :param value: The property value
        :raise TypeError: Invalid argument type
        :raise ValueError: If the name or the name is None or empty
        """
        # Field validity test
        if not is_string(field):
            raise TypeError("Field name must be a string")

        field = field.strip()
        if not field or ' ' in field:
            raise ValueError("Empty or invalid property field name '{0}'"
                             .format(field))

        # Name validity test
        if name is not None:
            if not is_string(name):
                raise TypeError("Property name must be a string")

            name = name.strip()

        if not name:
            # No name given: use the field name
            name = field

        self.__field = field
        self.__name = name
        self.__value = value


    def __call__(self, clazz):
        """
        Adds the property to the class iPOPO properties field.
        Creates the field if needed.
        
        :param clazz: The class to decorate
        :return: The decorated class
        :raise TypeError: If *clazz* is not a type
        """
        if not inspect.isclass(clazz):
            raise TypeError("@Property can decorate only classes, not '{0}'" \
                            .format(type(clazz).__name__))

        # Get the factory context
        context = _get_factory_context(clazz)

        # Set up the property in the class
        context.properties[self.__name] = self.__value

        # Associate the field to the property name
        context.properties_fields[self.__field] = self.__name

        # Inject a property in the class. The property will call an instance
        # level getter / setter, injected by iPOPO after the instance creation
        setattr(clazz, self.__field, \
                _ipopo_class_field_property(self.__name, self.__value,
                                            constants.IPOPO_PROPERTY_PREFIX))

        return clazz

# ------------------------------------------------------------------------------

def _get_specifications(specifications):
    """
    Computes the list of strings corresponding to the given specifications
    
    :param specifications: A string, a class or a list of specifications
    :return: A list of strings
    :raise ValueError: Invalid specification found
    """
    if not specifications:
        raise ValueError("No specifications given")

    if inspect.isclass(specifications):
        # Get the name of the class
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
        raise ValueError("Unhandled specifications type : {0}" \
                         .format(type(specifications).__name__))


class Provides:
    """
    @Provides decorator
    
    Defines an interface exported by a component.
    """
    def __init__(self, specifications=None, controller=None):
        """
        Sets up a provided service.
        A service controller can be defined to enable or disable the service.
        
        :param specifications: A list of provided interface(s) name(s)
                               (can't be empty)
        :param controller: Name of the service controller class field (optional)
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

            elif ' ' in controller:
                raise ValueError("Controller name contains spaces")

        self.__specifications = _get_specifications(specifications)
        self.__controller = controller


    def __call__(self, clazz):
        """
        Adds the provided service information to the class context iPOPO field.
        Creates the field if needed.
        
        :param clazz: The class to decorate
        :return: The decorated class
        :raise TypeError: If *clazz* is not a type
        """

        if not inspect.isclass(clazz):
            raise TypeError("@Provides can decorate only classes, not '{0}'" \
                            .format(type(clazz).__name__))

        # Get the factory context
        context = _get_factory_context(clazz)

        # Avoid duplicates (but keep the order)
        filtered_specs = []
        for spec in self.__specifications:
            if spec not in filtered_specs:
                filtered_specs.append(spec)

        # Store the service information
        context.provides.append((filtered_specs, self.__controller))

        if self.__controller:
            # Inject a property in the class. The property will call an instance
            # level getter / setter, injected by iPOPO after the instance creation
            setattr(clazz, self.__controller,
                    _ipopo_class_field_property(self.__controller, True,
                                            constants.IPOPO_CONTROLLER_PREFIX))

            # Inject the future controller methods
            setattr(clazz, constants.IPOPO_CONTROLLER_PREFIX \
                    + constants.IPOPO_GETTER_SUFFIX, None)
            setattr(clazz, constants.IPOPO_CONTROLLER_PREFIX \
                    + constants.IPOPO_SETTER_SUFFIX, None)

        return clazz

# ------------------------------------------------------------------------------

class Requires:
    """
    @Requires decorator
    
    Defines a required component
    """
    def __init__(self, field="", specification="", aggregate=False, \
                 optional=False, spec_filter=None):
        """
        Sets up the requirement
        
        :param field: The injected field
        :param specification: The injected service specification
        :param aggregate: If true, injects a list
        :param optional: If true, this injection is optional
        :param spec_filter: An LDAP query to filter injected services upon their
                            properties
        :raise TypeError: A parameter has an invalid type
        :raise ValueError: An error occurred while parsing the filter or an
                           argument is incorrect
        """
        if not field:
            raise ValueError("Empty field name.")

        if not is_string(field):
            raise TypeError("The field name must be a string, not {0}" \
                            .format(type(field).__name__))

        if ' ' in field:
            raise ValueError("Field name can't contain spaces.")

        self.__field = field
        self.__requirement = Requirement(_get_specifications(specification),
                                         aggregate, optional, spec_filter)

    def __call__(self, clazz):
        """
        Adds the requirement to the class iPOPO field
        
        :param clazz: The class to decorate
        :return: The decorated class
        :raise TypeError: If *clazz* is not a type
        """
        if not inspect.isclass(clazz):
            raise TypeError("@Provides can decorate only classes, not '{0}'" \
                            .format(type(clazz).__name__))

        # Set up the property in the class
        context = _get_factory_context(clazz)
        context.requirements[self.__field] = self.__requirement

        # Inject the field
        setattr(clazz, self.__field, None)

        return clazz

# ------------------------------------------------------------------------------

def Bind(method):
    """
    Bind callback decorator, called when a component is bound to a dependency.
    
    The decorated method must have the following prototype :
    
    .. python::
       def bind_method(self, injected_service, service_reference):
           '''
           Method called when a service is bound to the component
           
           :param injected_service: The injected service instance.
           :param service_reference: The injected service ServiceReference
           '''
           # ...
    
    If the service is a required one, the bind callback is called **before** the
    component is validated.
    
    The service reference can be stored *if its reference is deleted on unbind*.
    
    Exceptions raised by a bind callback are ignored.
    
    :param method: The decorated method
    :raise TypeError: The decorated element is not a valid function
    """
    if not inspect.isroutine(method):
        raise TypeError("@Bind can only be applied on functions")

    # Tests the number of parameters
    validate_method_arity(method, "service", "service_reference")

    _append_object_entry(method, constants.IPOPO_METHOD_CALLBACKS, \
                         constants.IPOPO_CALLBACK_BIND)
    return method


def Unbind(method):
    """
    Unbind callback decorator, called when a component dependency is unbound.
    
    The decorated method must have the following prototype :
    
    .. python::
       def unbind_method(self, injected_instance):
           '''
           Method called when a service is bound to the component
           
           :param injected_instance: The injected service instance.
           '''
           # ...
    
    If the service is a required one, the unbind callback is called **after**
    the component has been invalidated.
    
    Exceptions raised by an unbind callback are ignored.
    
    :param method: The decorated method
    :raise TypeError: The decorated element is not a valid function
    """
    if type(method) is not types.FunctionType:
        raise TypeError("@Unbind can only be applied on functions")

    # Tests the number of parameters
    validate_method_arity(method, "service", "service_reference")

    _append_object_entry(method, constants.IPOPO_METHOD_CALLBACKS, \
                         constants.IPOPO_CALLBACK_UNBIND)
    return method


def Validate(method):
    """
    Validation callback decorator, called when a component becomes valid,
    i.e. if all of its required dependencies has been injected.
    
    The decorated method must have the following prototype :
    
    .. python::
       def validation_method(self, bundle_context):
           '''
           Method called when the component is validated
           
           :param bundle_context: The component's bundle context
           '''
           # ...
    
    If the validation callback raises an exception, the component is considered
    not validated.
    
    If the component provides a service, the validation method is called before
    the provided service is registered to the framework.
    
    :param method: The decorated method
    :raise TypeError: The decorated element is not a valid function
    """
    if type(method) is not types.FunctionType:
        raise TypeError("@Validate can only be applied on functions")

    # Tests the number of parameters
    validate_method_arity(method, "bundle_context")

    _append_object_entry(method, constants.IPOPO_METHOD_CALLBACKS, \
                         constants.IPOPO_CALLBACK_VALIDATE)
    return method


def Invalidate(method):
    """
    Invalidation callback decorator, called when a component becomes invalid,
    i.e. if one of its required dependencies disappeared
    
    The decorated method must have the following prototype :
    
    .. python::
       def invalidation_method(self, bundle_context):
           '''
           Method called when the component is invalidated
           
           :param bundle_context: The component's bundle context
           '''
           # ...
    
    Exceptions raised by an invalidation callback are ignored.
    
    If the component provides a service, the invalidation method is called after
    the provided service has been unregistered to the framework.
    
    :param method: The decorated method
    :raise TypeError: The decorated element is not a function
    """

    if type(method) is not types.FunctionType:
        raise TypeError("@Invalidate can only be applied on functions")

    # Tests the number of parameters
    validate_method_arity(method, "bundle_context")

    _append_object_entry(method, constants.IPOPO_METHOD_CALLBACKS, \
                         constants.IPOPO_CALLBACK_INVALIDATE)
    return method

