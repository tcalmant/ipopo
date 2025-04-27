#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the RSA discovery provider

:author: Scott Lewis
"""

import json
import unittest
from typing import Any, TypeVar

from pelix.internals.registry import ServiceReference
from pelix.utilities import EventData

try:
    # Try to import modules
    import multiprocessing
    from multiprocessing import Queue

    # IronPython fails when creating a queue
    Queue()

    # Trick to avoid pytest hanging
    multiprocessing.set_start_method("spawn", force=True)
except ImportError:
    # Some interpreters don't have support for multiprocessing
    raise unittest.SkipTest("Interpreter doesn't support multiprocessing")

import pelix.framework
import pelix.rsa as rsa
from pelix.framework import create_framework
from pelix.ipopo.constants import use_ipopo
from pelix.rsa import ECF_ENDPOINT_CONTAINERID_NAMESPACE, RemoteServiceAdmin
from pelix.rsa.endpointdescription import EndpointDescription
from pelix.rsa.providers.discovery import EndpointAdvertiser, EndpointEvent
from pelix.rsa.topologymanagers import TopologyManager
from tests.utilities import WrappedProcess

TEST_ETCD_HOSTNAME = "localhost"
TEST_ETCD_TOPPATH = (
    "org.eclipse.ecf.provider.etcd3.container.Etcd3DiscoveryContainer"  # "/etcd3discovery.tests"
)

ENDPOINT_LISTENER_SCOPE = f"({ECF_ENDPOINT_CONTAINERID_NAMESPACE}=*)"

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

T = TypeVar("T")

# ------------------------------------------------------------------------------


def start_framework_for_advertise(state_queue: Queue, order_queue: Queue):
    """
    Starts a Pelix framework to advertise (via etcd) a helloimpl_xmlrpc
    remote service instance.  The tests can/will then discover this
    service advertisement and test the EndpointEventListener notification

    :param state_queue: Queue to communicate status
    :param order_queue: Queue to receive termination order
    """
    try:
        # Start the framework
        framework = create_framework(
            [
                "pelix.ipopo.core",
                "pelix.rsa.remoteserviceadmin",  # RSA implementation
                "pelix.http.basic",  # httpservice
                # xmlrpc distribution provider (opt)
                "pelix.rsa.providers.distribution.xmlrpc",
                # etcd discovery provider (opt)
                "pelix.rsa.providers.discovery.etcd3",
                "pelix.rsa.topologymanagers.basic",
                "samples.rsa.helloimpl_xmlrpc",
            ],
            {
                "ecf.xmlrpc.server.hostname": "localhost",
            },
        )
        framework.start()
        # start etcd3 discovery service client
        bc = framework.get_bundle_context()
        # Start an HTTP server, required by XML-RPC
        with use_ipopo(bc) as ipopo:
            ipopo.instantiate(
                "pelix.http.service.basic.factory",
                "http-server",
                {"pelix.http.address": "localhost", "pelix.http.port": 0},
            )
        from pelix.rsa.topologymanagers.basic import instantiate_basic_topology_manager
        instantiate_basic_topology_manager(bc)
        # instantiate and connect etcd3 discovery
        from pelix.rsa.providers.discovery.etcd3 import instantiate_etcd3_discovery_provider
        instantiate_etcd3_discovery_provider(bc,
                {"etcd.hostname": TEST_ETCD_HOSTNAME, \
                 "etcd.top_key": TEST_ETCD_TOPPATH})

        svc_ref = bc.get_service_reference(RemoteServiceAdmin, None)
        assert svc_ref is not None
        rsa = bc.get_service(svc_ref)
        # export the hello remote service via rsa
        # with the BasicTopologyManager, this will result
        # in publish via etcd
        hello_ref = bc.get_service_reference("org.eclipse.ecf.examples.hello.IHello")
        assert hello_ref is not None
        rsa.export_service(
            hello_ref,
            {
                "service.exported.interfaces": "*",
                "service.exported.configs": "ecf.xmlrpc.server",
            },
        )
        try:
            # Send that we are now ready
            state_queue.put("ready")
            # Wait until we receive the termination order
            order = order_queue.get(timeout=60)
            assert order == "quit"
        finally:
            # stop the framework gracefully
            framework.stop()
            framework.delete()
    except Exception as ex:
        state_queue.put(f"Error: {ex}")


class EtcdDiscoveryListenerTest(unittest.TestCase):

    def setUp(self):
        """
        Starts a local framework to register the
        TestEndpointEventListener
        """
        self.status_queue = Queue()
        self.order_queue = Queue()

        # start a local framework
        self.framework = create_framework(
            [
                "pelix.ipopo.core",
                "pelix.rsa.remoteserviceadmin",  # RSA implementation
                "tests.rsa.endpoint_event_listener",
                "pelix.rsa.providers.discovery.etcd3",
            ],
            {},
        )
        self.framework.start()
                # Start the framework and return TestEndpointEventListener
        context = self.framework.get_bundle_context()

        # start etcd3 discovery service client
        from pelix.rsa.providers.discovery.etcd3 import instantiate_etcd3_discovery_provider
        instantiate_etcd3_discovery_provider(context,
                {"etcd.hostname": TEST_ETCD_HOSTNAME, \
                 "etcd.top_key": TEST_ETCD_TOPPATH})

        with use_ipopo(context) as ipopo:
            #  create endpoint event listener
            self.listener = ipopo.instantiate(
                "etcd-test-endpoint-event-listener-factory",
                "etcd-test-endpoint-event-listener",
                {TopologyManager.ENDPOINT_LISTENER_SCOPE: ENDPOINT_LISTENER_SCOPE},
            )

    def prepareFrameworkProcess(self):
        """
        Starts a framework in separate process to advertise a helloimpl
        remote service
        """
        # start external framework that publishes remote service
        self.publisher_process = WrappedProcess(
            target=start_framework_for_advertise, args=[self.status_queue, self.order_queue]
        )
        self.publisher_process.start()
        state = self.status_queue.get(timeout=20)
        self.assertEqual(state, "ready")

    def tearDown(self):
        """
        Cleans up external publishing framework for next test
        """
        try:
            self.publisher_process.kill()
            self.publisher_process.join(5)
            self.publisher_process.close()
        finally:
            self.status_queue.close()
            self.order_queue.close()
            self.publisher = None

            # Stop the framework
            pelix.framework.FrameworkFactory.delete_framework()
            self.framework = None

    def test_etcd_discover(self):
        test_done_event = EventData()

        def test_handler_1(endpoint_event, matched_filter):
            try:
                self.assertTrue(matched_filter, ENDPOINT_LISTENER_SCOPE)
                self.assertIsNotNone(endpoint_event, "endpoint_event is None")
                self.assertTrue(isinstance(endpoint_event, EndpointEvent))
                ee_type = endpoint_event.get_type()
                self.assertTrue(ee_type == EndpointEvent.ADDED or ee_type == EndpointEvent.REMOVED)
                ee_ed = endpoint_event.get_endpoint_description()
                self.assertTrue(isinstance(ee_ed, EndpointDescription))
                self.assertIsNotNone(ee_ed.get_id(), "endpoint_description id is None")
                self.assertIsNotNone(
                    ee_ed.get_framework_uuid(),
                    "endpoint_description framework uuid is None",
                )

                interfaces = ee_ed.get_interfaces()
                # test that service interfaces is not None and is of type list
                self.assertIsNotNone(interfaces)
                self.assertTrue(isinstance(interfaces, type([])))
                self.assertTrue("org.eclipse.ecf.examples.hello.IHello" in interfaces)

                # Tell child process to quit
                self.order_queue.put("quit")

                # set the test_done_event, so tester thread will continue
                test_done_event.set()
            except Exception as e:
                test_done_event.raise_exception(e)

        # set the handler to the test code above
        self.listener.set_handler(test_handler_1)

        # Start the remote process
        self.prepareFrameworkProcess()

        # wait as much as 50 seconds to complete
        self.assertTrue(test_done_event.wait(50))

    def test_etcd_discover_remove(self):
        test_done_event = EventData()

        def test_handler_2(endpoint_event, matched_filter):
            try:
                if endpoint_event.get_type() == EndpointEvent.ADDED:
                    # send shutdown to trigger the removal
                    self.order_queue.put("quit")
                elif endpoint_event.get_type() == EndpointEvent.REMOVED:
                    # do tests
                    self.assertTrue(matched_filter, ENDPOINT_LISTENER_SCOPE)
                    self.assertIsNotNone(endpoint_event, "endpoint_event is None")
                    self.assertTrue(isinstance(endpoint_event, EndpointEvent))
                    ee_ed = endpoint_event.get_endpoint_description()
                    self.assertTrue(isinstance(ee_ed, EndpointDescription))
                    self.assertIsNotNone(ee_ed.get_id(), "endpoint_description id is None")
                    self.assertIsNotNone(
                        ee_ed.get_framework_uuid(),
                        "endpoint_description framework uuid is None",
                    )

                    interfaces = ee_ed.get_interfaces()
                    # test that service interfaces is not None and is of type list
                    self.assertIsNotNone(interfaces)
                    self.assertTrue(isinstance(interfaces, type([])))
                    self.assertTrue("org.eclipse.ecf.examples.hello.IHello" in interfaces)

                    # finally set the test_done_event, so tester thread will
                    # continue
                    test_done_event.set()
            except Exception as ex:
                test_done_event.raise_exception(ex)

        # set the handler to the test code above
        self.listener.set_handler(test_handler_2)

        # Start the remote process
        self.prepareFrameworkProcess()

        # wait as much as 60 seconds to complete
        self.assertTrue(test_done_event.wait(60))


class EtcdDiscoveryPublishTest(unittest.TestCase):

    def setUp(self):
        """
        Prepares a framework
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(
            [
                "pelix.ipopo.core",
                "pelix.shell.core",
                "pelix.http.basic",
                "pelix.rsa.remoteserviceadmin",
                "pelix.rsa.providers.distribution.xmlrpc",
                "pelix.rsa.providers.discovery.etcd3",
            ],
            {
                "ecf.xmlrpc.server.hostname": "localhost",
            },
        )
        self.framework.start()

        context = self.framework.get_bundle_context()
        # Start an HTTP server, required by XML-RPC
        with use_ipopo(context) as ipopo:
            ipopo.instantiate(
                "pelix.http.service.basic.factory",
                "http-server",
                {"pelix.http.address": "localhost", "pelix.http.port": 0},
            )
        from pelix.rsa.providers.discovery.etcd3 import instantiate_etcd3_discovery_provider
        instantiate_etcd3_discovery_provider(context, {"etcd.hostname": TEST_ETCD_HOSTNAME,
                 "etcd.top_key": TEST_ETCD_TOPPATH,
                 })
        self.advertiser = None
        self.rsa = None
        self.svc_reg = None
        self.export_reg = None
        self.eel_reg = None

    def tearDown(self):
        """
        Cleans up for next test
        """
        try:
            if self.eel_reg:
                self.eel_reg.unregister()
                self.eel_reg = None

            if self.svc_reg:
                self.svc_reg.unregister()
                self.svc_reg = None
            if self.export_reg:
                self.export_reg.close()
                self.export_reg = None
            if self.advertiser:
                self._unget_service(self._get_discovery_advertiser_sr())
                self.advertiser = None

            if self.rsa:
                self._unget_service(self._get_rsa_sr())
                self.rsa = None
        finally:
            # Stop the framework
            pelix.framework.FrameworkFactory.delete_framework()
            self.framework = None

    def _get_discovery_advertiser_sr(self) -> ServiceReference[EndpointAdvertiser]:
        assert self.framework is not None
        svc_ref = self.framework.get_bundle_context().get_service_reference(EndpointAdvertiser)
        assert svc_ref is not None
        return svc_ref

    def _get_rsa_sr(self) -> ServiceReference[RemoteServiceAdmin]:
        assert self.framework is not None
        svc_ref = self.framework.get_bundle_context().get_service_reference(RemoteServiceAdmin)
        assert svc_ref is not None
        return svc_ref

    def _get_service(self, sr: ServiceReference[T]) -> T:
        assert self.framework is not None
        return self.framework.get_bundle_context().get_service(sr)

    def _unget_service(self, sr: ServiceReference[Any]) -> None:
        assert self.framework is not None
        self.framework.get_bundle_context().unget_service(sr)

    def _get_advertiser(self):
        self.advertiser = self._get_service(self._get_discovery_advertiser_sr())
        return self.advertiser

    def _get_rsa(self):
        self.rsa = self._get_service(self._get_rsa_sr())
        return self.rsa

    def _register_svc(self):
        assert self.framework is not None
        spec = "test.svc"
        svc = object()
        return self.framework.get_bundle_context().register_service(spec, svc, {})

    def _export_svc(self):
        self.svc_reg = self._register_svc()
        self.export_reg = self._get_rsa().export_service(
            self.svc_reg.get_reference(),
            {
                rsa.SERVICE_EXPORTED_INTERFACES: "*",
                rsa.SERVICE_EXPORTED_CONFIGS: "ecf.xmlrpc.server",
            },
        )[0]
        return self.export_reg

    def test_get_discovery_advertiser(self):
        disc_adv_sr = self._get_discovery_advertiser_sr()
        self.assertIsNotNone(disc_adv_sr, "advertiser ref is null")
        self.advertiser = self._get_service(disc_adv_sr)
        self.assertIsNotNone(self.advertiser, "advertiser svc is null")

    def test_none_advertised(self):
        adv = self._get_advertiser()
        eps = adv.get_advertised_endpoints()
        self.assertDictEqual(eps, {}, "advertised endpoints not empty eps={0}".format(eps))

    def test_etcd_session(self):
        self.assertIsNotNone(self._get_advertiser()._session_id, "etcd._sessionid is null")

    def test_etcd_remote_exists(self):
        adv = self._get_advertiser()
        adv._get_value(adv._get_session_path())

    def test_etcd_advertise(self):
        adv = self._get_advertiser()
        export_reg = self._export_svc()
        ed = export_reg.get_description()
        ed_id = ed.get_id()
        ep_adv = adv.advertise_endpoint(ed)
        self.assertTrue(ep_adv, "advertise_endpoint failed")
        ep_key = adv._get_session_path() + "/" + ed_id
        # test for existence of ep id key
        ed_val = adv._get_value(ep_key)
        ep_dict = json.loads(ed_val)
        self.assertTrue(ep_dict['location'].startswith('ecfosgisvc'), 'retrieved endpoing does not have proper location field')
        # get advertised endpoints
        eps = adv.get_advertised_endpoints()
        # should be of length 1
        self.assertTrue(len(eps) == 1, "length of eps is not equal 1")
        # now unadvertise
        adv.unadvertise_endpoint(ed_id)
        try:
            adv._get_value(ep_key)
            self.fail("endpoint={0} still advertised after being removed".format(ed_id))
        except Exception:  # exception expected
            pass
        eps = adv.get_advertised_endpoints()
        self.assertTrue(
            len(eps) == 0,
            "length of eps should be 0 and is {0}".format(len(eps)),
        )

    def test_etcd_advertise_content(self):
        adv = self._get_advertiser()
        export_reg = self._export_svc()
        ed = export_reg.get_description()
        ed_id = ed.get_id()
        # get encoded version of endpoint description (dict)
        encoded_ep = adv._encode_description(ed)
        # advertise it
        adv.advertise_endpoint(ed)
        # get the string directly via http and key
        ed_val_str = adv._get_value("".join([adv._get_session_path(), "/", ed_id]))
        # decode the string into json object (dict)
        val_encoded = json.loads(ed_val_str)
        # compare the original dict with the one returned
        self.assertDictEqual(encoded_ep, val_encoded, "encoded endpoints not equal")
        # also check a couple of fields
        self.assertListEqual(
            encoded_ep["properties"],
            val_encoded["properties"],
            "encoded_ed_props and val_encoded_props are not equal",
        )
        # now unadvertise
        adv.unadvertise_endpoint(ed_id)
