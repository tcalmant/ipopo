# Using Python.Java Remote Services to Resolve Python Imports

:::{admonition} Authors
Scott Lewis
:::

## Introduction

As part of recent work on [iPOPO RSA](https://github.com/tcalmant/ipopo), an implementation of a python import hook [pep-302](https://peps.python.org/pep-0302/) was created so using remote services java bundles could resolve python packages.  On the java side, the [ModuleResolver](https://github.com/ECF/Py4j-RemoteServicesProvider/blob/master/bundles/org.eclipse.ecf.provider.direct/src/org/eclipse/ecf/provider/direct/ModuleResolver.java) service interface exposes the methods called by a python import hook to resolve a python module.

[Here](examples/org.eclipse.ecf.examples.importhook.module/src/org/eclipse/ecf/examples/importhook/module/ExampleBundleModuleResolver.java) is an example ModuleResolver service implementation for a python package named 'foo'.  Note that the PATH_PREFIX component property points to ['/python-src'](https://github.com/ECF/Py4j-RemoteServicesProvider/tree/master/examples/org.eclipse.ecf.examples.importhook.module/python-src/) inside built bundle.

### Requirements

This tutorial sample requires Karaf 4.4.6+ on Java 17 or higher for the server process and Python 3.10+ for the iPOPO sample application process, and 3.0.0+ of iPOPO

## To run this 'foo' ModuleResolver in [Karaf 4.4.6+](https://karaf.apache.org/download)

Download download karaf

```bash
# Download Karaf from https://karaf.apache.org/download.html
wget http://archive.apache.org/dist/karaf/4.4.6/apache-karaf-4.4.6.tar.gz
tar xzf apache-karaf-4.4.6.tar.gz
# start karaf
cd apache-karaf-4.4.6.tar.gz
./bin/karaf
```

# ECF Remote Services Features to Karaf

```
karaf@root()> repo-add https://download.eclipse.org/rt/ecf/latest/karaf-features.xml
Adding feature url https://download.eclipse.org/rt/ecf/latest/karaf-features.xml
```

### Install the feature that exposing the 'foo' package Module Resolver example

```
karaf@root()> feature:install ecf-rs-examples-python-importhook
(few seconds pass for download and install)
karaf@root()>
```
By default, a Python.Java gateway will be started and be listening for python connections on localhost:25333 (unless configured otherwise).  The 'foo' package ModuleResolver remote service will be available for resolving the 'foo' package.

### Start iPopo Example ImportHook Application

The iPOPO project has a python-side Python.Java Distribution Provider, and a sample application to connect to the Java server at localhost:25333 and then resolve and run the code in the 'foo' package.  This sample application is [here](https://github.com/tcalmant/ipopo/blob/v3/samples/run_rsa_py4j_importhook.py).

To start the sample from a shell (python 3.10+):

```
python -m samples.run_rsa_py4j_importhook
```

If the Karaf server is running the python sample application will produce output like this

```
Attempting connect to Python.Java OSGi server listening at 25333...
** Pelix Shell prompt **
$ If the py4j localhost connect above succeeds, the code import for package foo.bar.baz
will be resolved by the OSGi server with an a active instance of a ModuleResolver
service implementation from the example in this bundle: org.eclipse.ecf.examples.importhook.module
The code for this bundle is here: 
https://github.com/ECF/Py4j-RemoteServicesProvider/tree/master/examples/org.eclipse.ecf.examples.importhook.module
There are instructions for running an instance of this server in the RSA importhook tutorial at
https://ipopo.readthedocs.io/en/v3/tutorials/index.html

...importing Bar class from foo.bar.baz package

foo imported
imported bar
baz loaded
foobar loaded

...Bar class imported
...creating an instance of Bar...

Foo.init
Bar.init

...Bar instance created.  The print output between the lines starting with '...' is from foo package code
```

The messages 'foo imported, imported bar' are produced from running the python code returned by the ModuleResolver service from [/python-src](https://github.com/ECF/Py4j-RemoteServicesProvider/tree/master/examples/org.eclipse.ecf.examples.importhook.module/python-src).

If the Karaf server is not running/listening on localhost:25333, the python attempt to connect will produce a connect error

```
py4j.protocol.Py4JNetworkError: An error occurred while trying to connect to the Java server (127.0.0.1:25333)

```
