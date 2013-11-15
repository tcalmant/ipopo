#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Defines some iPOPO constants

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: Apache License 2.0
:version: 0.5.5
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
__version_info__ = (0, 5, 5)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Pelix
from pelix.constants import BundleException

# Standard library
import contextlib

# ------------------------------------------------------------------------------

IPOPO_SERVICE_SPECIFICATION = "pelix.ipopo.core"
""" iPOPO service specification string """

# ------------------------------------------------------------------------------

HANDLER_REQUIRES = 'ipopo.requires'
""" The @Requires handler ID """

HANDLER_PROVIDES = 'ipopo.provides'
""" The @Provides handler ID """

HANDLER_PROPERTY = 'ipopo.properties'
""" The @Property handler ID """

# ------------------------------------------------------------------------------

# Injected class fields
IPOPO_METHOD_CALLBACKS = "__ipopo_callbacks__"
""" Contains the list of callback types this method is decorated for """

IPOPO_METHOD_FIELD_CALLBACKS = "__ipopo_field_callbacks__"
""" Contains a list of tuples (field, callback type) """

IPOPO_FACTORY_CONTEXT = "__ipopo_factory_context__"
""" Storage of the FactoryContext object """

IPOPO_INSTANCES = "__ipopo_instances__"
""" List of configured instantiations """

# Method called by the injected property (must be injected in the instance)
IPOPO_GETTER_SUFFIX = "_getter"
IPOPO_SETTER_SUFFIX = "_setter"
IPOPO_PROPERTY_PREFIX = "_ipopo_property"
IPOPO_CONTROLLER_PREFIX = "_ipopo_controller"

# ------------------------------------------------------------------------------

# Callbacks
IPOPO_CALLBACK_BIND = "BIND"
""" Bind: called when a dependency is injected """

IPOPO_CALLBACK_BIND_FIELD = "BIND_FIELD"
""" BindField: called when a dependency is injected in the given field """

IPOPO_CALLBACK_UPDATE = "UPDATE"
"""
Update: called when the properties of an injected dependency have been updated
"""

IPOPO_CALLBACK_UPDATE_FIELD = "UPDATE_FIELD"
"""
UpdateField: called when the properties of a dependency injected in the given
field have been updated
"""

IPOPO_CALLBACK_UNBIND = "UNBIND"
""" Unbind: called when a dependency is about to be removed """

IPOPO_CALLBACK_UNBIND_FIELD = "UNBIND_FIELD"
"""
UnbindFielld: called when a dependency is about to be removed from the given
field
"""

IPOPO_CALLBACK_VALIDATE = "VALIDATE"
""" Validate: Called when all mandatory dependencies have been bound """

IPOPO_CALLBACK_INVALIDATE = "INVALIDATE"
""" Invalidate: Called when one the mandatory dependencies is unbound """

# Properties
IPOPO_INSTANCE_NAME = "instance.name"
""" Name of the component instance """

IPOPO_REQUIRES_FILTERS = "requires.filters"
""" Dictionary to override @Requires filters """

IPOPO_AUTO_RESTART = "pelix.ipopo.auto_restart"
"""
If True, the component will be re-instantiated after its bundle has been updated
"""

# ------------------------------------------------------------------------------

def get_ipopo_svc_ref(bundle_context):
    """
    Retrieves a tuple containing the service reference to iPOPO and the service
    itself

    :param bundle_context: The calling bundle context
    :return: The reference to the iPOPO service and the service itself,
             None if not available
    """
    # Look after the service
    ref = bundle_context.get_service_reference(IPOPO_SERVICE_SPECIFICATION)
    if ref is None:
        return None

    try:
        # Get it
        svc = bundle_context.get_service(ref)

    except BundleException:
        # Service reference has been invalidated
        return None

    # Return both the reference (to call unget_service()) and the service
    return (ref, svc)


@contextlib.contextmanager
def use_ipopo(bundle_context):
    """
    Utility context to use the iPOPO service safely in a "with" block.
    It looks after the the iPOPO service and releases its reference when exiting
    the context.

    :param bundle_context: The calling bundle context
    :return: The iPOPO service
    :raise BundleException: Service not found
    """
    # Get the service and its reference
    ref_svc = get_ipopo_svc_ref(bundle_context)
    if ref_svc is None:
        raise BundleException("iPOPO service not available")

    try:
        # Give the service
        yield ref_svc[1]

    finally:
        try:
            # Release it
            bundle_context.unget_service(ref_svc[0])

        except BundleException:
            # Service might have already been unregistered
            pass

# ------------------------------------------------------------------------------

class IPopoEvent(object):
    """
    An iPOPO event descriptor.
    """
    REGISTERED = 1
    """ A component factory has been registered """

    INSTANTIATED = 2
    """ A component has been instantiated, but not yet validated """

    VALIDATED = 3
    """ A component has been validated """

    INVALIDATED = 4
    """ A component has been invalidated """

    BOUND = 5
    """ A reference has been injected in the component """

    UNBOUND = 6
    """ A reference has been removed from the component """

    KILLED = 9
    """ A component has been killed (removed from the list of instances) """

    UNREGISTERED = 10
    """ A component factory has been unregistered """


    def __init__(self, kind, factory_name, component_name):
        """
        Sets up the iPOPO event

        :param kind: Kind of event
        :param factory_name: Name of the factory associated to the event
        :param component_name: Name of the component instance associated to the
                               event
        """
        self.__kind = kind
        self.__factory_name = factory_name
        self.__component_name = component_name


    def get_component_name(self):
        """
        Retrieves the name of the component associated to the event

        :return: the name of the component
        """
        return self.__component_name


    def get_factory_name(self):
        """
        Retrieves the name of the factory associated to the event

        :return: the name of the component factory
        """
        return self.__factory_name


    def get_kind(self):
        """
        Retrieves the kind of event

        :return: the kind of event
        """
        return self.__kind
