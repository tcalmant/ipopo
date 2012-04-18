#!/usr/bin/python
#-- Content-Encoding: UTF-8 --
"""
HTTP Service demo for Pelix / iPOPO : the servlet bundle

:author: Thomas Calmant
:license: GPLv3
"""

# ------------------------------------------------------------------------------

# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory, Provides, Validate, \
    Invalidate, Property, Instantiate, Requires

# ------------------------------------------------------------------------------

@ComponentFactory(name="HelloWorldFactory")
@Instantiate(name="HelloWorld")
@Property("path", "servlet.path", "/hello")
@Provides(specifications="demo.HttpServlet")
# The component requires an extra information service, if available
@Requires("extra_info", "demo.ExtraInfoService", optional=True)
class HelloWorldServlet(object):
    """
    A simple hello world servlet for HTTP service
    """
    def __init__(self):
        """
        Sets up members
        """
        self.extra_info = None


    def do_GET(self, handler):
        """
        HTTP Servlet API : handle a GET request
        
        :param handler: The request handler associated to the call
        """
        # Prepare extra info, if available
        if self.extra_info is None:
            info = "<p>No extra information available.</p>"

        else:
            info = """<ul>
<li>Time : {time}</li>
<li>Platform : {platform}</li>
<li>PID : {pid}</li>""".format(time=self.extra_info.get_time(),
                               platform=self.extra_info.get_platform(),
                               pid=self.extra_info.get_pid())

        # Generate the page
        page = """<html>
<head>
<title>Hello, World !</title>
</head>
<body>
<h1>Hello, World !</h1>
<h2>Extra information</h2>
{extra_info}
</body>
</html>""".format(extra_info=info)

        # Send the page
        handler.send_data(page)
