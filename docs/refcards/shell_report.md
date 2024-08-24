# Shell reports

Pelix/iPOPO comes with a bundle, `pelix.shell.report`, which provides
commands to generate reports describing the current framework and its
host. This main purpose of this feature is to debug a faulty framework
by grabbing all available information. It can also be used to have a
quick overview of the operating system, either to check the installation
environment or to identify the host machine.

## Setup

This feature requires an active Pelix Shell (`pelix.shell.core`) and a
UI. See [](./shell.md) for more information on this subject. The iPOPO
service is not required for this feature to work.

It can therefore be started programmatically using the following
snippet:

```python
# Start the framework, with the required bundles and the report bundle
framework = create_framework(
    ["pelix.shell.core", "pelix.shell.report"])

# ... or install & start it using the BundleContext
bundle_context.install_bundle("pelix.shell.report").start()
```

It can only be installed from a Shell UI using the command
`start pelix.shell.report`.

## Usage

The bundle provides the following commands in the `report` namespace:

| Command | Description |
|----|----|
| `clear` | Clears the last report |
| `levels` | Lists the available levels of reporting |
| `make [<levels ...>]` | Prepares a report with the indicated levels (all levels if none set) |
| `show [<levels ...>]` | Shows the latest report. Prepares it if levels have been indicated |
| `write <filename>` | Write the latest report as a JSON file |

## Report levels

The reports are made of multiple "level information" sections. They
describe the current state of the application and its environment.

Here are some of the available levels.

### Framework information

| Level             | Description                                        |
|-------------------|----------------------------------------------------|
| `pelix_basic`     | Framework properties and version                   |
| `pelix_bundles`   | Bundles ID, name, version, state and location      |
| `pelix_services`  | Services ID, bundle and properties                 |
| `ipopo_factories` | Description of iPOPO factories (with their bundle) |
| `ipopo_instances` | Details of iPOPO instances                         |

### Process information

| Level | Description |
|----|----|
| `process` | Details about the current process (PID, user, working directory, ...) |
| `threads` | Lists the current process threads and their stacktrace |

### Python information

| Level | Description |
|----|----|
| `python` | Python interpreter details (version, compiler, path, ...) |
| `python_modules` | Lists all Python modules imported by the application |
| `python_path` | Lists the content of the Python Path |

### Host information

| Level | Description |
|----|----|
| `os` | Details about the OS (version, architecture, CPUs, ...) and the host name |
| `os_env` | Lists the environment variables and their value |
| `network` | Lists the IPs (v4 and v6) of the host, its name and FQDN. |

### Group levels

Some levels are groups of lower levels. They are subject to change,
therefore the following table is given as an indication. Always refer to
the `report.levels` shell command to check available ones.

| Level | Description |
|----|----|
| `pelix` | Combines `pelix_infos`, `pelix_bundles` and `pelix_services` |
| `ipopo` | Combines `ipopo_factories` and `ipopo_instances` |
| `app` | Combines `os`, `os_env`, `process`, `python` and `python_path` |
| `debug` | Combines `app` (except `os_env`), `pelix`, `ipopo` and `python_modules` |
| `standard` | Like `debug`, but without `pelix_services` nor `ipopo_instances` |
| `full` | Combines `debug`, `os_env`, `network` and `threads` |

Those *groups* were defined according to the most common combinations of
levels used during iPOPO development and live setup.
