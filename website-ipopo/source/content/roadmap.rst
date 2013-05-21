.. Project road map

Road map
########

This road map is given as an *indication* of the future features of iPOPO, but
it might not be fully respected.

Feel free to post feature requests or contributions on
`GitHub <https://github.com/tcalmant/ipopo/issues?state=open>`_ or on the
`users mailing list <http://groups.google.com/group/ipopo-users>`_.


High priority features
**********************

Those features are required for the associated release version.

+----------------------+---------+---------------------------------------------+
| Name                 | Version | Description                                 |
+======================+=========+=============================================+
| iPOPO Handlers       | 0.5.1   | Handlers should be services used by         |
|                      |         | the iPOPO core instance managers            |
+----------------------+---------+---------------------------------------------+
| @RequiresMap         | 0.5.1   | New handler for iPOPO: injects a map, the   |
|                      |         | key being computed according to the service |
|                      |         | properties                                  |
+----------------------+---------+---------------------------------------------+
| Package installation | 0.6     | Enhance the install_package() method        |
|                      |         | implementation                              |
+----------------------+---------+---------------------------------------------+


Medium priority features
************************

Those feature won't block a release if they are missing.

+---------------+---------+----------------------------------------------------------------------------+
| Name          | Version | Description                                                                |
+===============+=========+============================================================================+
| Documentation | 0.5.1   | Add more documentation upon the methods of Pelix                           |
|               |         | and iPOPO                                                                  |
+---------------+---------+----------------------------------------------------------------------------+
| Tutorials     | 0.5.1   | Write more tutorials for Pelix, iPOPO and the                              |
|               |         | provided services                                                          |
+---------------+---------+----------------------------------------------------------------------------+
| BundleLevel   | 0.5.2   | Add a bundle level, as described in this                                   |
|               |         | `blog <http://eclipsesource.com/blogs/2009/06/10/osgi-and-start-levels/>`_ |
+---------------+---------+----------------------------------------------------------------------------+
| Finder/Loader | 0.7     | Implement a PEP-302 Finder/Loader to control the                           |
|               |         | whole module import process                                                |
+---------------+---------+----------------------------------------------------------------------------+

Low priority features
*********************

Those features are not associated to any milestone in the development process.

+-------------+--------------------------------------------------------------+
| Name        | Description                                                  |
+=============+==============================================================+
| LogService  | Replace the direct usage of the ``logging`` package by a set |
|             | of services: LogService (used by writers), LogListeners,     |
|             | LogWriter, ...                                               |
+-------------+--------------------------------------------------------------+
| ConfigAdmin | White-board pattern based configuration service              |
+-------------+--------------------------------------------------------------+
| Benchmarks  | Benchmark suite to detect performance problems               |
+-------------+--------------------------------------------------------------+
| C-Bridge    | Define a standard/easy way to use C libraries as bundles     |
+-------------+--------------------------------------------------------------+
| Interfaces  | Provide more specification tools, to validate that a service |
|             | implements the specifications it claims                      |
+-------------+--------------------------------------------------------------+
