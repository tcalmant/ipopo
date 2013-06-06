#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Sample JVM launch with jPype
"""
# Documentation strings format
__docformat__ = "restructuredtext en"

# Boot module version
__version__ = "1.0.0"

# ------------------------------------------------------------------------------

# jPype
import jpype

# ------------------------------------------------------------------------------

def start(vm_library=None, *args):
    """
    Starts a JVM with the given parameters
    
    :raise ValueError: Invalid parameter
    """
    # Get the JVM library path
    if not vm_library:
        # Use the one used during compilation if needed
        vm_library = jpype.getDefaultJVMPath()

    # Load the JVM
    jpype.startJVM(vm_library, *args)

def stop():
    """
    Stops the JVM.
    
    :return: True if the JVM has been stopped, else False
    """
    # Stop the JVM
    jpype.shutdownJVM()

def hello(name):
    """
    Prints a greeting message
    """
    jpype.java.lang.System.out.println("Hello " + str(name) + "!")


def map_test():
    HashMap = jpype._jclass.JClass("java.util.HashMap")
    javaMap = HashMap()
    javaMap.put("answer", 42)
    print("JavaMap=" + javaMap.toString())

# ------------------------------------------------------------------------------

start()
hello("World")
map_test()
stop()