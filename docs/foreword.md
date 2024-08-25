# Foreword

This section describes the purpose and goals of the iPOPO project, as
well as some background history.

## What is iPOPO ?

iPOPO is a Python-based Service-Oriented Component Model (SOCM). It is
split into two parts:

* Pelix, a dynamic service platform
* iPOPO, the SOCM framework, hence the name.

Both are inspired on two popular Java technologies for the development
of long-lived applications: the [OSGi Service Platform](https://www.osgi.org/) and the
[iPOJO component model](https://web.archive.org/web/20210616112915/http://felix.apache.org/documentation/subprojects/apache-felix-ipojo.html).

iPOPO allows to conceive long-running and modular IT services in Python.

About the name, iPOPO is inspired from iPOJO, which stands for *injected
Plain Old Java Object*. Java being replaced by Python, the name became
iPOPO. The logo comes from the similarity of pronunciation with the
french word for the hippo: *hippopotame*.

By the way, I pronounce the name iPOPO the french way, *i.e.* /i.pɔ.pɔ/
([International Phonetic Alphabet](https://en.wikipedia.org/wiki/International_Phonetic_Alphabet)).
The english way, *i.e.* /aɪ.pɔ.pɔ/, is the most commonly used by the
users I had the chance to talk to.

## A bit of history

During my PhD thesis, I had to monitor applications built as multiple
instances of OSGi frameworks and based on iPOJO components. This
required to access some OS-specific low-level methods and was initially
done in Java with JNA.

To ease the development of probes, the monitoring code has been
translated to Python. At first, it was only a set of scripts without any
relations, but as the project grown, it was necessary to develop a
framework to handle those various parts and to link them together. In
order to be consistent, I decided to develop a component model similar
to what my employer used in Java, iPOJO, and keeping the concepts of
OSGi.

A first draft, called `python.injections` was developed in December 2011.
It was a proof of concept which was good enough for my employer,
[isandlaTech](http://www.cohorte-technologies.com/fr/) (now Cohorte
Technologies), to allow the development of what would become iPOPO.

The first public release was version 0.3 in April 2012, under the GPLv3
license. In November 2013, iPOPO adopts the Apache Software License 2.0
with release 0.5.5.

On March 2015, release 0.6 dropped support for Python 2.6. Since then,
the development slowed down as the core framework reached a stable state.

After a long period without updates nor user requests since 2018, iPOPO was
considered mature enough to earn its new major version: iPOPO 1.0 was released
in January 2020

An iPOPO 2.0 branch was started contributors in 2020, trying to bring an
asynchronous approach to the framework. The branch stalled as the requirement
for retro-compatibility was too complex to achieve.

After a long pause of development, some of the iPOPO users I personally know
came to me requesting an upgrade to support Python 3.10.
Instead of trying to have a version that works from Python 2.7 to 3.10, like we
tried with iPOPO v2, I decided we should drop older Python versions and focus
on currently maintained ones. Retro-compatibility can be achieved by using
iPOPO 1.x on older Python versions and communicate with newer deployments using
Remote Services or Remote Services Admin.

iPOPO 3 is the current framework version, first released in August 2024.
It dropped support for Python versions older than 3.10 and started to use type
hints to help developers working on very large projects.

## SOA and SOCM in Python

The Service-Oriented Architecture (SOA) consists in linking objects
through provided contracts (services) registered in a service registry.

A service is an object associated to properties describing it, including
the names of the contracts it implements. It is stored in the service
registry of the framework by the service provider. The provider or the
service itself (they are often the same) must handle the requirements,
*i.e.* looking for the services required to work and handling their late
un/registration.

A component is an object instantiated and handled by an instance manager
created by iPOPO. The manager handles the life cycle of the component,
looking for its dependencies and handling their late registration,
unregistration and replacement. It eases the development and allows a
lot of dynamism in an application.

The conclusion is that the parts of an application which only provide a
feature can be written as a simple service, whereas parts using other
elements of the application should be written as components.

Continue to [installation](./installation.md), the
[quick-start](./quickstart.md) or the
[tutorials](./tutorials/index.md).
