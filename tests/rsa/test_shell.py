#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the RSA shell commands

:author: Thomas Calmant
"""

import os
import unittest
from io import StringIO

import pelix.constants
import pelix.framework
import pelix.shell.beans as beans
from pelix.constants import FRAMEWORK_UID, SERVICE_ID, BundleException
from pelix.ipopo.constants import use_ipopo
from pelix.rsa import ENDPOINT_FRAMEWORK_UUID, ENDPOINT_ID
from pelix.shell import ShellService

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class ShellTest(unittest.TestCase):
    """
    Tests for the RSA Shell tests
    """

    def setUp(self):
        """
        Prepares a framework and a registers a service to export
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(
            [
                "pelix.ipopo.core",
                "pelix.shell.core",
                "pelix.rsa.shell",
                "pelix.http.basic",
                "pelix.rsa.remoteserviceadmin",
                "pelix.rsa.providers.distribution.xmlrpc",
            ],
            {"ecf.xmlrpc.server.hostname": "localhost"},
        )
        self.framework.start()

        # Start an HTTP server, required by XML-RPC
        context = self.framework.get_bundle_context()
        with use_ipopo(context) as ipopo:
            ipopo.instantiate(
                "pelix.http.service.basic.factory",
                "http-server",
                {"pelix.http.address": "localhost", "pelix.http.port": 0},
            )

        # Get the shell service
        svc_ref = context.get_service_reference(ShellService)
        assert svc_ref is not None
        self.shell = context.get_service(svc_ref)

    def tearDown(self):
        """
        Cleans up for next test
        """
        # Stop the framework
        pelix.framework.FrameworkFactory.delete_framework()

        self.framework = None
        self.svc_ref = None

    def _run_command(self, command, *args, **kwargs):
        """
        Runs the given command and returns the output stream. A keyword
        argument 'session' can be given to use a custom ShellSession.
        """
        # Format command
        if args:
            command = command.format(*args)

        try:
            # Get the given session
            session = kwargs["session"]
            str_output = kwargs["output"]
            str_output.truncate(0)
            str_output.seek(0)
        except KeyError:
            # No session given
            str_output = StringIO()
            session = beans.ShellSession(beans.IOHandler(None, str_output))

        # Run command
        self.shell.execute(command, session)
        return str_output.getvalue()

    def test_lists(self):
        """
        Tests the basic list* commands in Pelix RSA
        """
        self._run_command("listconfigs")
        self._run_command("listproviders")
        self._run_command("listcontainers")
        self._run_command("listexports")
        self._run_command("listimports")
        self._run_command("showdefaults")

    @staticmethod
    def _extract_list(cmd_output):
        """
        Parses the list printed by listexports/listimports

        :param cmd_output: A command output
        :return: A list of exported/imported endpoints
        """
        results = []
        for line in cmd_output.splitlines()[3:-1]:
            if line.startswith("+"):
                continue

            items = [item.strip() for item in line.split("|") if item]
            if items:
                results.append(items)
        return results

    def test_import_export(self):
        """
        Tests service export/import with
        """
        assert self.framework is not None
        # Prepare a service to export
        context = self.framework.get_bundle_context()
        svc_reg = context.register_service("toto", object(), {})
        svc_ref = svc_reg.get_reference()
        svc_id = svc_ref.get_property(SERVICE_ID)
        str_id = str(svc_id)

        # Assert that the service is not yet exported
        for line in self._extract_list(self._run_command("listexports")):
            if line[2] == str_id:
                self.fail("Service ID already in exports list")

        # Export it in a custom EDEF file
        filename = "test.xml"
        try:
            os.remove(filename)
        except OSError:
            pass

        self.assertFalse(os.path.exists(filename))
        self._run_command("exportservice {0} filename={1}", str_id, filename)
        self.assertTrue(os.path.exists(filename))

        # Assert that the service is exported
        for line in self._extract_list(self._run_command("listexports")):
            if line[2] == str_id:
                break
        else:
            self.fail("Export endpoint not found")

        # Import it from the EDEF file
        self._run_command("importservice {0}", filename)

        # Check if we imported the service
        imp_ref = context.get_service_reference("toto", "(service.imported=*)")
        assert imp_ref is not None
        fw_uid = context.get_property(FRAMEWORK_UID)
        self.assertEqual(imp_ref.get_property(ENDPOINT_FRAMEWORK_UUID), fw_uid)

        imp_id = str(imp_ref.get_property(SERVICE_ID))
        imp_ed_id = str(imp_ref.get_property(ENDPOINT_ID))
        for line in self._extract_list(self._run_command("listimports")):
            if line[0] == imp_ed_id and line[2] == imp_id:
                break
        else:
            self.fail("Service not imported")

        # Un-import service
        self._run_command("unimportservice {0}", imp_ed_id)
        self.assertNotIn(imp_id, self._run_command("listimports"))
        self.assertNotIn(imp_ed_id, self._run_command("listimports"))
        self.assertRaises(BundleException, context.get_service, imp_ref)

        # Get the endpoint ID of the exported service
        for line in self._extract_list(self._run_command("listexports")):
            if line[2] == str_id:
                svc_ed_id = line[0]
                break
        else:
            self.fail("Couldn't find endpoint ID")

        # Simple test
        self._run_command("listexports {0}", svc_ed_id)

        # Un-export service
        self._run_command("unexportservice {0}", svc_ed_id)

        # Assert that the service is not yet exported
        self.assertNotIn(svc_ed_id, self._run_command("listexports"))
        for line in self._extract_list(self._run_command("listexports")):
            if line[2] == str_id:
                self.fail("Service ID still in exports list")
