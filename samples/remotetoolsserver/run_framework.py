import pelix.framework as pelix

# For Pydev debugging
# import sys;sys.path.append(r'C:\eclipse-2025-03a\eclipse\plugins\org.python.pydev.core_13.0.2.202503021229\pysrc')
# import pydevd;pydevd.settrace()

# These represent all the bundles/modules
bundles = (
    # ipopo framework core impl
    "pelix.ipopo.core",
    # remote service admin (RSA) impl
    "pelix.rsa.remoteserviceadmin",
    # RSA distribution provider using py4j.  When the framework is started,
    # this will try to connect to a Java process using the ecf py4j
    # distribution provider.  The expected ports set to the
    # ecf.py4j.javaport and ecf.py4j.pythonport properties in the
    # create_framework call below
    "pelix.rsa.providers.distribution.py4j",
    # the RemoteToolsFastMCP server implemented as a pelix bundle
    # See the declaration of the RemoteToolsFastMCPServer in
    # samples/remotetoolserver.server.py..
    "samples.remotetoolsserver.server",
)

# Use the utility method to create, run and delete the framework
framework = pelix.create_framework(
    # NOTE: A Java Py4j distribution provider when started by the
    # pelix framework will try to connect to java/osgi process assumed to be
    # running at 25333 on localhost. If the java/osgi server is not listening
    # the start of the pelix.rsa.providers.distribution.p4j provider
    # will raise a connect exception.
    bundles,
    {
        "ecf.py4j.javaport": 25333,
        "ecf.py4j.pythonport": 25334,
        # FastMCP server name property set here
        "remotetoolsfastmpcserver.name": "Sample RemoteTools FastMCP Server",
    },
)
# everything actually started here
framework.start()
# wait for framework to stop itself here
framework.wait_for_stop()
