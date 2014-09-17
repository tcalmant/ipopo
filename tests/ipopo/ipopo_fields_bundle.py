#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Bundle defining multiple component factories for iPOPO tests

:author: Thomas Calmant
"""
from pelix.ipopo.decorators import ComponentFactory, Property, Provides, \
    Requires, Validate, Invalidate, Unbind, Bind, BindField, \
    UnbindField, Update, UpdateField

from pelix.constants import OBJECTCLASS

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

SVC_A = "service.a"
SVC_B = "service.b"

FACTORY_A = "ipopo.fieldtests.a"
FACTORY_B = "ipopo.fieldtests.b"
FACTORY_C = "ipopo.fieldtests.c"
FACTORY_D = "ipopo.fieldtests.d"
PROP_TEST = "test.value"

BIND_A = "bind.a"
BIND_B = "bind.b"
BIND_FIELD_A = "bind.field.a"
BIND_FIELD_B = "bind.field.b"
UPDATE_A = "update.a"
UPDATE_B = "update.b"
UPDATE_FIELD_A = "update.field.a"
UPDATE_FIELD_B = "update.field.b"
UNBIND_A = "unbind.a"
UNBIND_B = "unbind.b"
UNBIND_FIELD_A = "unbind.field.a"
UNBIND_FIELD_B = "unbind.field.b"

# ------------------------------------------------------------------------------
# Providers (auto-instantiated)


@ComponentFactory(FACTORY_A)
@Provides(SVC_A)
@Property("_prop", PROP_TEST)
class TestComponentA(object):
    """
    Provider of service A
    """
    def __init__(self):
        """
        Constructor
        """
        self._prop = None

    @Validate
    def validate(self, context):
        """
        Validation
        """
        self._prop = None

    def change(self, value):
        """
        Changes the value of the service property
        """
        self._prop = value

    @Invalidate
    def invalidate(self, context):
        """
        Invalidation
        """
        self._prop = None


@ComponentFactory(FACTORY_B)
@Provides(SVC_B)
@Property("_prop", PROP_TEST)
class TestComponentB(object):
    """
    Provider of service B
    """
    def __init__(self):
        """
        Constructor
        """
        self._prop = None

    @Validate
    def validate(self, context):
        """
        Validation
        """
        self._prop = None

    def change(self, value):
        """
        Changes the value of the service property
        """
        self._prop = value

    @Invalidate
    def invalidate(self, context):
        """
        Invalidation
        """
        self._prop = None

# ------------------------------------------------------------------------------
# Consumer


@ComponentFactory(FACTORY_C)
@Requires("_svc_a", SVC_A)
@Requires("_svc_b", SVC_B)
class Consumer(object):
    """
    Sample consumer
    """
    def __init__(self):
        """"
        Constructor
        """
        self.states = []
        self._svc_a = None
        self._svc_b = None

    def change_a(self, value):
        """
        Changes the property value of service A
        """
        self._svc_a.change(value)

    def change_b(self, value):
        """
        Changes the property value of service B
        """
        self._svc_b.change(value)

    @Bind
    def bind(self, svc, ref):
        """
        Bound
        """
        if SVC_A in ref.get_property(OBJECTCLASS):
            self.states.append(BIND_A)

        elif SVC_B in ref.get_property(OBJECTCLASS):
            self.states.append(BIND_B)

    @BindField("_svc_a")
    def bind_field_a(self, field, svc, ref):
        """
        Bound field
        """
        self.states.append(BIND_FIELD_A)

    @BindField("_svc_b")
    def bind_field_b(self, field, svc, ref):
        """
        Bound field
        """
        self.states.append(BIND_FIELD_B)

    @Update
    def update(self, svc, ref, old_props):
        """
        Updated dependency
        """
        if SVC_A in ref.get_property(OBJECTCLASS):
            self.states.append(UPDATE_A)

        elif SVC_B in ref.get_property(OBJECTCLASS):
            self.states.append(UPDATE_B)

    @UpdateField("_svc_a")
    def update_field_a(self, field, svc, ref, old_props):
        """
        Updated dependency
        """
        self.states.append(UPDATE_FIELD_A)

    @UpdateField("_svc_b")
    def update_field_b(self, field, svc, ref, old_props):
        """
        Updated dependency
        """
        self.states.append(UPDATE_FIELD_B)

    @Unbind
    def unbind(self, svc, ref):
        """
        Unbound
        """
        if SVC_A in ref.get_property(OBJECTCLASS):
            self.states.append(UNBIND_A)

        elif SVC_B in ref.get_property(OBJECTCLASS):
            self.states.append(UNBIND_B)

    @UnbindField("_svc_a")
    def unbind_field_a(self, field, svc, ref):
        """
        Unbound field
        """
        self.states.append(UNBIND_FIELD_A)

    @UnbindField("_svc_b")
    def unbind_field_b(self, field, svc, ref):
        """
        Unbound field
        """
        self.states.append(UNBIND_FIELD_B)

# ------------------------------------------------------------------------------

# Other consumer


@ComponentFactory(FACTORY_D)
@Requires("_svc_a", SVC_A)
@Requires("_svc_b", SVC_B, optional=True)
class ConsumerBindIfValid(object):
    """
    Sample consumer to test the "if_valid" flag
    """
    def __init__(self):
        """"
        Constructor
        """
        self.states = []
        self._svc_a = None
        self._svc_b = None

    def change_b(self, value):
        """
        Changes the property value of service B
        """
        self._svc_b.change(value)

    @BindField("_svc_a")
    def bind_field_a(self, field, svc, ref):
        """
        Bound field
        """
        self.states.append(BIND_FIELD_A)

    @BindField("_svc_b", True)
    def bind_field_b(self, field, svc, ref):
        """
        Bound field
        """
        self.states.append(BIND_FIELD_B)

    @UpdateField("_svc_b", True)
    def update_field_b(self, field, svc, ref, old_props):
        """
        Bound field
        """
        self.states.append(UPDATE_FIELD_B)

    @UnbindField("_svc_b", True)
    def unbind_field_b(self, field, svc, ref):
        """
        Bound field
        """
        self.states.append(UNBIND_FIELD_B)
