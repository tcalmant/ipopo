#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Run RSA with py4java distribution and discovery module

:author: Scott Lewis
:copyright: Copyright 2020, Scott Lewis
:license: Apache License 2.0
:version: 1.0.2

..

    Copyright 2020 Scott Lewis

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        https://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

import pelix.framework as pelix

# ------------------------------------------------------------------------------
# Module version
__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"


def main() -> None:
    # Set the initial bundles
    bundles = (
        "pelix.ipopo.core",
        "pelix.shell.core",
        "pelix.shell.ipopo",
        "pelix.shell.console",
        # RSA implementation
        "pelix.rsa.remoteserviceadmin",
        # Basic topology manager (opt)
        "pelix.rsa.topologymanagers.basic",
        # RSA shell commands (opt)
        "pelix.rsa.shell",
        "pelix.rsa.providers.distribution.py4j",
    )

    print("Attempting connect to Python.Java OSGi server listening at 25333...")
    # Use the utility method to create, run and delete the framework
    framework = pelix.create_framework(
        bundles, {"ecf.py4j.javaport": 25333, "ecf.py4j.pythonport": 25334, "ecf.py4j.useimporthook": True}
    )
    framework.start()

    from pelix.rsa.topologymanagers.basic import instantiate_basic_topology_manager
    instantiate_basic_topology_manager(framework.get_bundle_context())

    print("If the py4j localhost connect above succeeds, the code import for package foo.bar.baz")
    print("will be resolved by the OSGi server with an a active instance of a ModuleResolver")
    print("service implementation from the example in this bundle: org.eclipse.ecf.examples.importhook.module")
    print("The code for this bundle is here: ")
    print("https://github.com/ECF/Py4j-RemoteServicesProvider/tree/master/examples/org.eclipse.ecf.examples.importhook.module")
    print("There are instructions for running an instance of this server in the RSA importhook tutorial at")
    print("https://ipopo.readthedocs.io/en/v3/tutorials/index.html")
    print("")
    print("...importing Bar class from foo.bar.baz package")
    print("")
    from foo.bar.baz import Bar
    print("")
    print("...Bar class imported")
    print("...creating an instance of Bar...")
    print("")
    b = Bar()
    print("")
    print("...Bar instance created.  The print output between the lines starting with '...' is from foo package code")

    try:
        framework.wait_for_stop()
    except KeyboardInterrupt:
        framework.stop()


if __name__ == "__main__":
    main()
