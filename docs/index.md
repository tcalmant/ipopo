# Welcome to iPOPO

```{image} ./_static/logo_texte_200.png
:alt: iPOPO logo
:align: right
```

iPOPO is a Python-based Service-Oriented Component Model (SOCM) built on top of
Pelix, a dynamic service platform. It helps building modular, long-running
applications from loosely coupled components and services, with explicit
lifecycle management and runtime composition.

It is especially relevant for software engineers building gateways,
automation stacks, distributed backends and extensible platforms that need
operational visibility and controlled evolution over time.

The framework adapts to Python ideas popularized by
[iPOJO](https://web.archive.org/web/20210616112915/http://felix.apache.org/documentation/subprojects/apache-felix-ipojo.html)
and [OSGi](https://www.osgi.org/). It was designed by Thomas Calmant in his
[PhD Thesis](https://theses.hal.science/tel-01254286/file/CALMANT_2015_archivage.pdf)
(in French), in continuity with the earlier [iPOJO work](https://theses.hal.science/tel-00347935/document) by Clément Escoffier.

:::{important}
This documentation targets the current iPOPO 3.x line and Python 3.10+.
:::

## Why iPOPO

- Runtime-managed components with explicit lifecycle and dependency injection.
- A service registry with dynamic binding between providers and consumers.
- Built-in operational tooling such as the Pelix shell, Configuration Admin,
	Event Admin, HTTP services and remote service support.
- A Python-first developer experience with regular modules, type hints and
	Protocol-based service specifications.

## Start here

This documentation is divided into three main parts.
The [quickstart](./quickstart.md) guides you through installation and your
first components.
The [reference cards](./refcards/index.md) detail the core concepts,
decorators and services.
The [tutorials](./tutorials/index.md) show how to use the built-in services in
real examples.

If you are evaluating the project for adoption, also look at
[who uses iPOPO](./users.md) and the [release notes](./changelog.md).
You can also take a look at the slides of the
[iPOPO tutorial](https://github.com/tcalmant/ipopo-tutorials/releases)
to have a quick overview of iPOPO.

## Project license

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
