# Welcome to iPOPO

```{image} ./_static/logo_texte_200.png
:alt: iPOPO logo
:align: right
```

iPOPO is a Python-based Service-Oriented Component Model (SOCM) based on Pelix,
a dynamic service platform.
They are inspired by two popular Java technologies for the development of
long-lived applications: the
[iPOJO](https://web.archive.org/web/20210616112915/http://felix.apache.org/documentation/subprojects/apache-felix-ipojo.html)
component model and the [OSGi](https://www.osgi.org/) Service Platform.
iPOPO enables the conception of long-running and modular IT services.
The iPOJO component model was designed by Clément Escoffier in his
[PhD Thesis](https://theses.hal.science/tel-00347935/document) (in French),
while the iPOPO component model was designed by Thomas Calmant in his
[PhD Thesis](https://theses.hal.science/tel-01254286/file/CALMANT_2015_archivage.pdf)
(in French).

This documentation is divided into three main parts.
The [quickstart](./quickstart.md) will guide you to install iPOPO and write your
first components.
The [reference cards](./refcards/index.md) details the various concepts of iPOPO.
Finally, the [tutorials](./tutorials/index.md) explain how to use the various
built-in services of iPOPO.
You can also take a look at the slides of the
[iPOPO tutorial](https://github.com/tcalmant/ipopo-tutorials/releases)
to have a quick overview of iPOPO.

iPOPO is released under the terms of the
[Apache Software License 2.0](https://www.apache.org/licenses/LICENSE-2.0.html).
It depends on a fork of [`jsonrpclib`](https://github.com/joshmarshall/jsonrpclib),
named [`jsonrpclib-pelix`](https://github.com/tcalmant/jsonrpclib).
The documentation of this library is available on
[GitHub](https://github.com/tcalmant/jsonrpclib).

## Support

If you have any question which hasn't been answered in the documentation,
please ask on the
[users' mailing list](https://groups.google.com/forum/#!forum/ipopo-users) or
in the [GitHub Discussions](https://github.com/tcalmant/ipopo/discussions).

As always, all contributions to the documentation and the code are very
appreciated: bugs and features requests can be submitted using the
[Issue Tracker](https://github.com/tcalmant/ipopo/issues) on GitHub.
Questions about the development of iPOPO itself should be asked on the
[developers' mailing list](https://groups.google.com/g/ipopo-dev) or
in the [GitHub Discussions](https://github.com/tcalmant/ipopo/discussions).

```{include} contents.md.inc
```
