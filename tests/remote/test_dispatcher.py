#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the Remote Services Exports Dispatcher

:author: Thomas Calmant
"""

# Remote Services
import pelix.remote
import pelix.remote.beans as beans

# Pelix
import pelix.constants
import pelix.framework

# Standard library
import sys
import uuid
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

ADDED = 1
UPDATED = 2
REMOVED = 3

# ------------------------------------------------------------------------------


class Exporter(object):
    """
    Service exporter
    """
    def __init__(self, context, name=None, configs=None):
        """
        Sets up members
        """
        self.context = context
        self.events = []
        self.raise_exception = False

        self.endpoint = None
        self.name = name or 'test.endpoint'
        self.configs = configs[:] if configs else ['test.config']

    def clear(self):
        """
        Clears the listener state
        """
        del self.events[:]

    def export_service(self, svc_ref, name, fw_uid):
        """
        Endpoint registered
        """
        self.events.append(ADDED)
        service = self.context.get_service(svc_ref)
        self.endpoint = beans.ExportEndpoint(str(uuid.uuid4()), fw_uid,
                                             self.configs, self.name,
                                             svc_ref, service, {})
        return self.endpoint

    def update_export(self, endpoint, new_name, old_properties):
        """
        Endpoint updated
        """
        self.events.append(UPDATED)
        if self.raise_exception:
            raise NameError("Update exception: new name refused")

    def unexport_service(self, endpoint):
        """
        Endpoint removed
        """
        self.events.append(REMOVED)


class Listener(object):
    """
    Export endpoints listener
    """
    def __init__(self):
        """
        Sets up members
        """
        self.events = []
        self.raise_exception = False

    def clear(self):
        """
        Clears the listener state
        """
        del self.events[:]

    def endpoints_added(self, endpoints):
        """
        Endpoints registered
        """
        if endpoints:
            self.events.append(ADDED)

        if self.raise_exception:
            raise Exception("Endpoints added exception")

    def endpoint_updated(self, endpoint, old_props):
        """
        Endpoint updated
        """
        self.events.append(UPDATED)
        if self.raise_exception:
            raise Exception("Endpoints updated exception")

    def endpoint_removed(self, endpoint):
        """
        Endpoint removed
        """
        self.events.append(REMOVED)
        if self.raise_exception:
            raise Exception("Endpoints removed exception")

# ------------------------------------------------------------------------------


class DispatcherTest(unittest.TestCase):
    """
    Tests for the Remote Services dispatcher
    """
    def setUp(self):
        """
        Sets up the test
        """
        # Compatibility issue between Python 2 & 3
        if sys.version_info[0] < 3:
            self.assertCountEqual = self.assertItemsEqual

        # Create the framework
        self.framework = pelix.framework.create_framework(['pelix.ipopo.core'])
        self.framework.start()

        # Install the registry
        context = self.framework.get_bundle_context()
        context.install_bundle("pelix.remote.dispatcher").start()

        # Get the framework UID
        self.framework_uid = context.get_property(
            pelix.constants.FRAMEWORK_UID)

        # Get the service
        svc_ref = context.get_service_reference(
            pelix.remote.SERVICE_DISPATCHER)
        self.service = context.get_service(svc_ref)

    def tearDown(self):
        """
        Cleans up for next test
        """
        # Stop the framework
        pelix.framework.FrameworkFactory.delete_framework(self.framework)

        self.framework = None
        self.service = None

    def testEmpty(self):
        """
        Tests the behavior of the dispatcher without listener
        """
        # Register an exported service
        context = self.framework.get_bundle_context()
        service = object()
        svc_reg = context.register_service(
            "sample.spec", service,
            {pelix.remote.PROP_EXPORTED_INTERFACES: "*"})

        # Look for the endpoint
        self.assertEqual(self.service.get_endpoints(), [],
                         "An endpoint has been created")

        # Unregister the service
        svc_reg.unregister()

    def testExporterAfterRegistration(self):
        """
        Tests the behavior of the dispatcher with a exporter
        """
        # Register an exported service
        context = self.framework.get_bundle_context()
        service = object()

        for raise_exception in (False, True):
            # Register the exported service
            svc_reg = context.register_service(
                "sample.spec", service,
                {pelix.remote.PROP_EXPORTED_INTERFACES: "*"})

            # Prepare a exporter
            exporter = Exporter(context)
            exporter.raise_exception = raise_exception

            # Register it
            exporter_reg = context.register_service(
                pelix.remote.SERVICE_EXPORT_PROVIDER,
                exporter, {})

            # Check the state of the exporter
            self.assertListEqual(exporter.events, [ADDED],
                                 "Exporter not notified")
            exporter.clear()

            # Look for the endpoint
            endpoints = self.service.get_endpoints()
            self.assertEqual(len(endpoints), 1,
                             "The endpoint has not been created")
            endpoint = endpoints[0]
            self.assertIs(endpoint.instance, service)

            # Check access
            self.assertIs(self.service.get_endpoint(endpoint.uid), endpoint,
                          "Different endpoint on UID access")

            # Update the service
            svc_reg.set_properties({"some": "property"})
            if raise_exception:
                # The new properties have been refused
                self.assertListEqual(exporter.events, [UPDATED, REMOVED],
                                     "Exporter not notified of name removal")

            else:
                # Check the state of the exporter
                self.assertListEqual(exporter.events, [UPDATED],
                                     "Exporter not notified of update")
            exporter.clear()

            # Unregister the exported service
            svc_reg.unregister()

            if raise_exception:
                # Exception raised: the exporter has not been notified
                self.assertListEqual(exporter.events, [],
                                     "Exporter notified of ignored removal")

            else:
                # Check the state of the exporter
                self.assertListEqual(exporter.events, [REMOVED],
                                     "Exporter not notified of removal")
            exporter.clear()

            # Ensure there is no more endpoint
            self.assertEqual(self.service.get_endpoints(), [],
                             "Endpoint still there")
            self.assertIsNone(self.service.get_endpoint(endpoint.uid),
                              "Endpoint still there")

            # Unregister the service
            exporter_reg.unregister()

    def testExporterBeforeRegistration(self):
        """
        Tests the behavior of the dispatcher with a exporter
        """
        # Register an exported service
        context = self.framework.get_bundle_context()
        service = object()

        for raise_exception in (False, True):
            # Prepare a exporter
            exporter = Exporter(context)
            exporter.raise_exception = raise_exception

            # Register it
            exporter_reg = context.register_service(
                pelix.remote.SERVICE_EXPORT_PROVIDER,
                exporter, {})

            # Register the exported service
            svc_reg = context.register_service(
                "sample.spec", service,
                {pelix.remote.PROP_EXPORTED_INTERFACES: "*"})

            # Check the state of the exporter
            self.assertListEqual(exporter.events, [ADDED],
                                 "Exporter not notified")
            exporter.clear()

            # Look for the endpoint
            endpoints = self.service.get_endpoints()
            self.assertEqual(len(endpoints), 1,
                             "The endpoint has not been created")
            endpoint = endpoints[0]
            self.assertIs(endpoint.instance, service)

            # Check access
            self.assertIs(self.service.get_endpoint(endpoint.uid), endpoint,
                          "Different endpoint on UID access")

            # Update the service
            svc_reg.set_properties({"some": "property"})
            if raise_exception:
                # The new properties have been refused
                self.assertListEqual(exporter.events, [UPDATED, REMOVED],
                                     "Exporter not notified of name removal")

            else:
                # Check the state of the exporter
                self.assertListEqual(exporter.events, [UPDATED],
                                     "Exporter not notified of update")
            exporter.clear()

            # Unregister the exported service
            svc_reg.unregister()

            if raise_exception:
                # Exception raised: the exporter has not been notified
                self.assertListEqual(exporter.events, [],
                                     "Exporter notified of ignored removal")

            else:
                # Check the state of the exporter
                self.assertListEqual(exporter.events, [REMOVED],
                                     "Exporter not notified of removal")
            exporter.clear()

            # Ensure there is no more endpoint
            self.assertEqual(self.service.get_endpoints(), [],
                             "Endpoint still there")
            self.assertIsNone(self.service.get_endpoint(endpoint.uid),
                              "Endpoint still there")

            # Unregister the service
            exporter_reg.unregister()

    def testListenerBefore(self):
        """
        Tests the notification of endpoint listeners
        """
        # Register an exported service
        context = self.framework.get_bundle_context()
        service = object()

        for name_error in (True, False):
            for raise_exception in (False, True):
                # Prepare a listener
                listener = Listener()
                listener.raise_exception = raise_exception
                listener_reg = context.register_service(
                    pelix.remote.SERVICE_EXPORT_ENDPOINT_LISTENER,
                    listener, {})

                # Register the exported service
                svc_reg = context.register_service(
                    "sample.spec", service,
                    {pelix.remote.PROP_EXPORTED_INTERFACES: "*"})

                # Check the state of the listener
                self.assertListEqual(listener.events, [],
                                     "Listener notified too soon")
                listener.clear()

                # Prepare a exporter
                exporter = Exporter(context)
                exporter.raise_exception = name_error
                exporter_reg = context.register_service(
                    pelix.remote.SERVICE_EXPORT_PROVIDER,
                    exporter, {})

                # Check the state of the listener
                self.assertListEqual(listener.events, [ADDED],
                                     "Listener not notified")
                listener.clear()

                # Update the service
                svc_reg.set_properties({"some": "property"})
                if name_error:
                    # The new properties have been refused
                    self.assertListEqual(
                        listener.events, [REMOVED],
                        "Listener not notified of name removal")

                else:
                    # Check the state of the exporter
                    self.assertListEqual(listener.events, [UPDATED],
                                         "Listener not notified of update")
                listener.clear()

                # Unregister the exported service
                svc_reg.unregister()

                if name_error:
                    # Exception raised: the listener has not been notified
                    self.assertListEqual(
                        listener.events, [],
                        "Listener notified of ignored removal")

                else:
                    # Check the state of the listener
                    self.assertListEqual(listener.events, [REMOVED],
                                         "Listener not notified of removal")
                listener.clear()

                # Unregister the services
                exporter_reg.unregister()
                listener_reg.unregister()

    def testListenerAfter(self):
        """
        Tests the notification of endpoint listeners
        """
        # Prepare an exported service
        context = self.framework.get_bundle_context()
        service = object()

        for raise_exception in (False, True):
            # Prepare a exporter
            exporter = Exporter(context)
            exporter_reg = context.register_service(
                pelix.remote.SERVICE_EXPORT_PROVIDER,
                exporter, {})

            # Register the exported service
            svc_reg = context.register_service(
                "sample.spec", service,
                {pelix.remote.PROP_EXPORTED_INTERFACES: "*"})

            # Prepare a listener
            listener = Listener()
            listener.raise_exception = raise_exception
            listener_reg = context.register_service(
                pelix.remote.SERVICE_EXPORT_ENDPOINT_LISTENER,
                listener, {})

            # Check the state of the listener
            self.assertListEqual(listener.events, [ADDED],
                                 "Listener not notified")
            listener.clear()

            # Unregister the exporter
            exporter_reg.unregister()

            # Check the state of the listener
            self.assertListEqual(listener.events, [REMOVED],
                                 "Listener not notified of removal")
            listener.clear()

            # Unregister the exported service
            svc_reg.unregister()

            # Check the state of the listener
            self.assertListEqual(listener.events, [],
                                 "Listener notified of removal")
            listener.clear()

            # Unregister the services
            listener_reg.unregister()

    def testGetEndpoints(self):
        """
        Tests the behavior of the get_endpoints() method
        """
        context = self.framework.get_bundle_context()

        # Register exporters
        exporterA = Exporter(context, "nameA", ["configA"])
        exporterA_reg = context.register_service(
            pelix.remote.SERVICE_EXPORT_PROVIDER,
            exporterA, {})

        exporterB = Exporter(context, "nameB", ["configB"])
        exporterB_reg = context.register_service(
            pelix.remote.SERVICE_EXPORT_PROVIDER,
            exporterB, {})

        # Register the remote service
        service = object()
        svc_reg = context.register_service(
            "sample.spec", service,
            {pelix.remote.PROP_EXPORTED_INTERFACES: "*"})

        # Get all endpoints
        self.assertCountEqual([exporterA.endpoint, exporterB.endpoint],
                              self.service.get_endpoints(),
                              "Invalid result for get_endpoints()")

        # Get endpoint by name
        self.assertListEqual([exporterA.endpoint],
                             self.service.get_endpoints(name="nameA"),
                             "Invalid result for get_endpoints(name)")
        self.assertListEqual([exporterB.endpoint],
                             self.service.get_endpoints(name="nameB"),
                             "Invalid result for get_endpoints(name)")

        # Get endpoint by configuration
        self.assertListEqual([exporterA.endpoint],
                             self.service.get_endpoints(kind="configA"),
                             "Invalid result for get_endpoints(kind)")
        self.assertListEqual([exporterB.endpoint],
                             self.service.get_endpoints(kind="configB"),
                             "Invalid result for get_endpoints(kind)")

        # Filter with both
        self.assertListEqual([exporterA.endpoint],
                             self.service.get_endpoints("configA", "nameA"),
                             "Invalid result for get_endpoints(kind, name)")

        # Filter with no result
        self.assertListEqual([],
                             self.service.get_endpoints("configB", "nameA"),
                             "Invalid result for get_endpoints(kind, name)")

        # Unregister exporter B
        exporterB_reg.unregister()

        # Get all endpoints
        self.assertListEqual([exporterA.endpoint],
                             self.service.get_endpoints(),
                             "Endpoint of B still in get_endpoints()")

        # Unregister service
        svc_reg.unregister()

        # Get all endpoints
        self.assertListEqual([], self.service.get_endpoints(),
                             "Endpoint of A still in get_endpoints()")

        # Unregister exporter A
        exporterA_reg.unregister()

    def testExportReject(self):
        """
        Tests the "pelix.remote.export.reject" property
        """
        spec_1 = "sample.spec.1"
        full_spec_1 = "python:/" + spec_1
        spec_2 = "sample.spec.2"
        full_spec_2 = "python:/" + spec_2
        spec_3 = "sample.spec.3"
        full_spec_3 = "python:/" + spec_3

        # Register an exporter
        context = self.framework.get_bundle_context()
        exporter = Exporter(context)
        context.register_service(pelix.remote.SERVICE_EXPORT_PROVIDER,
                                 exporter, {})

        # Register an exported service: No filter
        service = object()
        svc_reg = context.register_service(
            [spec_1, spec_2, spec_3], service,
            {pelix.remote.PROP_EXPORTED_INTERFACES: "*",
             pelix.remote.PROP_EXPORT_REJECT: None})

        # Look for the endpoint: all services must be exported
        endpoint = self.service.get_endpoints()[0]
        self.assertCountEqual([full_spec_1, full_spec_2, full_spec_3],
                              endpoint.specifications)
        svc_reg.unregister()

        # Check with a string
        svc_reg = context.register_service(
            [spec_1, spec_2, spec_3], service,
            {pelix.remote.PROP_EXPORTED_INTERFACES: "*",
             pelix.remote.PROP_EXPORT_REJECT: spec_1})

        # Look for the endpoint: all services must be exported
        endpoint = self.service.get_endpoints()[0]
        self.assertCountEqual([full_spec_2, full_spec_3],
                              endpoint.specifications)
        svc_reg.unregister()

        for reject in ([spec_1], [spec_1, spec_2]):
            # Register the service
            svc_reg = context.register_service(
                [spec_1, spec_2, spec_3], service,
                {pelix.remote.PROP_EXPORTED_INTERFACES: "*",
                 pelix.remote.PROP_EXPORT_REJECT: reject})

            # Compute exported interfaces
            exported = ['python:/' + spec for spec
                        in set([spec_1, spec_2, spec_3]).difference(reject)]

            # Check it
            endpoint = self.service.get_endpoints()[0]
            self.assertCountEqual(exported, endpoint.specifications)

            # Unregister the service
            svc_reg.unregister()

        # Reject everything
        svc_reg = context.register_service(
            [spec_1, spec_2, spec_3], service,
            {pelix.remote.PROP_EXPORTED_INTERFACES: "*",
             pelix.remote.PROP_EXPORT_REJECT: [spec_1, spec_2, spec_3]})
        self.assertListEqual([], self.service.get_endpoints(),
                             "Endpoint registered while it exports nothing")
        svc_reg.unregister()

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
