# Pelix Shell

Most of the time, it is necessary to access a Pelix application locally
or remotely in order to monitor it, to update its components or simply
to check its sanity. The easiest to do those tasks is to use the Pelix
Shell: it provides an extensible set of commands that allows to work on
bundles, iPOPO components, ...

The shell is split into two parts:

* the core shell, handling and executing commands
* the UI, which handles input/output operations with the user

Pelix comes with some bundles providing shell commands for various
actions, and a few UI implementations. Feel free to implement and,
maybe, publish new commands UIs according to your needs.

In order to use the shell, the `pelix.shell.core` bundle must be
installed and running. It doesn't require iPOPO and can therefore be
used in minimalist applications.

## Provided user interfaces

Pelix includes 3 main user interfaces:

* Text UI: the one to use when running a basic Pelix application
* Remote Shell: useful when managing an application running on a server
* XMPP Shell: useful to access applications behind firewalls

### Common script arguments

Before looking at the available user interfaces, note that all of them
support arguments to handle the Initial Configuration files (see
[](./init_config.rst)).

In addition to their specific arguments, the scripts starting the user
interfaces also accept the following ones:

| Argument | Description |
|----|----|
| `-h`, `--help` | Prints the script usage |
| `--version` | Prints the script version |
| `-D KEY=VALUE` | Sets up a framework property |
| `-v`, `--verbose` | Sets the logger to DEBUG mode |
| `--init FILE` | Start by running a Pelix shell script |
| `--run FILE` | Run a Pelix shell script then exit |
| `-c FILE`, `--conf FILE` | Use a configuration file, above the system configuration |
| `-C FILE`, `--exclusive-conf FILE` | Use a configuration file, ignore the system configuration |
| `-e`, `--empty-conf` | Don't use any initial configuration |
| `--trusted-folder PATH` | Also look for a `.pelix.conf` file in this folder, and put it first in the Python path (repeatable) |

The scripts don't trust the working folder, which can be shared or untrusted:
they don't load its `.pelix.conf` file, and its modules can't be imported (the
scripts remove it from `sys.path`, where `python -m` puts it, and set the
`pelix.path.cwd` framework property to false). Use `--trusted-folder .` to
trust it, as Pelix 3.2 did.

### Text UI

The Text UI is the easiest way to manage or test your programs with
Pelix/iPOPO. It provides the most basic yet complete interaction with
the Pelix Shell core service.

If it is available, the Text UI relies on `readline` to provide command
and arguments completion.

#### Script startup

The text (or console) UI can be started using the
`python -m pelix.shell` command. This command will start a Pelix
framework, with iPOPO and the most commonly used shell command
providers.

This script only accepts the common shell parameters.

#### Programmatic startup

This UI is provided by the `pelix.shell.console` bundle. It is a raw
bundle, which does not provide a component factory: the UI is available
while the bundle is active. There is no configuration available when
starting the Text UI programmatically.

### Remote Shell

Pelix frameworks are often started on remote locations, but still need
to be managed with the Pelix shell. Instead of using an SSH connection
to work on a foreground server, you can use the Pelix Remote Shell.

The Pelix Remote Shell is a simple interface to the Pelix Shell core
service of its framework instance, based on a TCP server. Unlike the
console UI, multiple users can connect the framework at the same time,
each with his own shell session (variables, ...).

By default, the remote shell starts a TCP server listening the local
interface (*localhost*) on port 9000. Every TCP client must log in (see
[](#remote-shell-authentication)), and a server without TLS only accepts to listen
on a loopback address, so that no password crosses the network in clear text.

To listen on another address, set up OpenSSL certificates. The server will have its
own certificate, which should be checked by the clients, and by default each client
will have to connect with its own certificate, signed by an authority recognized by
the server.
See [](#how-to-prepare-certificates-for-the-remote-shell) for more information
on how to setup this kind of certificates.

:::{note}
TLS features and arguments are available only if the Python
interpreters fully provides the `ssl` module, *i.e.* if it has been
built with OpenSSL.
:::

#### Script startup

The remote shell UI can be started using the
`python -m pelix.shell.remote` command. This command will start a Pelix
framework with iPOPO, and will start a Python console locally.

In addition to the common parameters, the script accepts the following
ones:

| Argument | Default | Description |
|----|----|----|
| `--no-input` | *not set* | If set, don't start the Python console (useful for server/daemon mode) |
| `-a ADDR`, `--address ADDR` | localhost | Server binding address |
| `-p PORT`, `--port PORT` | 9000 | Server binding port |
| `--unix PATH` | `None` | Listen on a Unix socket instead of an address and port (see [](#remote-shell-unix-socket)). Refused with the TLS arguments |
| `--ca-chain FILE` | `None` | Path to the certificate authority chain file (to authenticate clients), required with `--cert` unless `--client-auth` is `none` |
| `--client-auth MODE` | `required` | Client certificates: `required`, `optional` or `none` (see `pelix.shell.ssl.client_auth`) |
| `--cert FILE` | `None` | Path to the server certificate file |
| `--key FILE` | `None` | Path to the server private key file |
| `--key-password PASSWORD` | `None` | Password of the server private key |

#### Programmatic startup

The remote shell is provided as the `ipopo-remote-shell-factory`
component factory defined in the `pelix.shell.remote` bundle. You should
use the constant `pelix.shell.FACTORY_REMOTE_SHELL` instead of the
factory name when instantiating the component.

This factory accepts the following properties:

| Name | Default | Description |
|----|----|----|
| `pelix.shell.address` | localhost | Server binding address |
| `pelix.shell.port` | 9000 | Server binding port |
| `pelix.shell.unix.path` | `None` | Path of a Unix socket to listen on, instead of the address and port (see [](#remote-shell-unix-socket)) |
| `pelix.shell.unix.check_peer` | `True` | Refuse the clients of a Unix socket run by another user than the server (root excepted), when the system tells it |
| `pelix.shell.ssl.ca` | `None` | Path to the clients certificate authority chain file |
| `pelix.shell.ssl.cert` | `None` | Path to the server's SSL certificate file |
| `pelix.shell.ssl.key` | `None` | Path to the server's private key |
| `pelix.shell.ssl.key_password` | `None` | Password of the server's private key |
| `pelix.shell.ssl.client_auth` | `required` | Client certificates: `required` (refused without one), `optional` (verified if presented, else a password login) or `none` (never asked: password logins only) |
| `pelix.shell.max_line_length` | 65536 | Longest line, in bytes, a client can send. `0` removes the limit |
| `pelix.shell.idle_timeout` | 3600 | Seconds without input before a session is closed. `0` removes the limit |
| `pelix.shell.login_timeout` | 60 | Seconds a client gets to finish the TLS handshake and to log in. `0` removes the limit |
| `pelix.shell.max_clients` | 32 | Maximum number of simultaneous clients. `0` removes the limit |

The last four properties protect the server from its clients: a line longer than
the limit, including data sent without any end of line, closes the session, as
does an idle session or a client which doesn't finish its TLS handshake or its
login in time. The TLS handshake is done in the thread of the client, so a client
which never finishes it doesn't delay the others. Connections past the maximum
number of clients are closed as soon as they are accepted.

:::{versionadded} 3.2.3
The `pelix.shell.max_line_length`, `pelix.shell.idle_timeout`,
`pelix.shell.login_timeout` and `pelix.shell.max_clients` properties. Before, a
client could make the server buffer an endless line, keep a thread forever, or
block every new connection by never finishing its TLS handshake.
:::

:::{warning}
`pelix.shell.ssl.ca` is not optional when `pelix.shell.ssl.cert` is set, unless
`pelix.shell.ssl.client_auth` is `none`.

Without an authority chain, the client certificates would be validated against
the **system trust store**: any certificate signed by any publicly trusted
authority would be accepted, by a shell which can install and start arbitrary
bundles. Since iPOPO 3.3.0, the remote shell refuses to start in that case
(iPOPO 3.2.2 only logged an error). It also refuses an authority chain with the
`none` mode, where it would never be used.
:::

:::{versionchanged} 3.3.0
The `pelix.shell.auth.required` property is removed: a TCP client must always log
in. The `pelix.shell.ssl.client_auth` property and the `--client-auth` argument are
added, and a server without TLS refuses to listen on another address than a
loopback one.
:::

#### Remote shell Unix socket

Instead of a TCP address and port, the remote shell can listen on a Unix
domain socket, which only the user running the framework can open. Set the
`pelix.shell.unix.path` property (or the `--unix` argument of the script) to
the path of the socket. The `pelix.shell.address` and `pelix.shell.port`
properties are then ignored, and `get_access()` returns `(path, None)`.

```python
ipopo.instantiate(
    pelix.shell.FACTORY_REMOTE_SHELL,
    "remote-shell",
    {"pelix.shell.unix.path": "/run/user/1000/myapp/shell.sock"},
)
```

To connect it, use a client able to open a Unix socket, like `nc -U` or `socat`:

```bash
nc -U /run/user/1000/myapp/shell.sock
socat - UNIX-CONNECT:/run/user/1000/myapp/shell.sock
```

With a password login, prefer `socat` with its `READLINE` address: it gives line
editing and a history, and its `noecho` option hides what is typed after the
password prompt (`nc` shows the password on the screen, as the terminal echoes
it):

```bash
socat "READLINE,history=$HOME/.myapp_shell_history,noecho=Password: " \
    UNIX-CONNECT:/run/user/1000/myapp/shell.sock
```

The `exit` (or `quit`) command, or an end of file (`Ctrl-D`), ends the session.
When the remote shell stops, it waits up to `STOP_TIMEOUT` seconds for the
sessions to end, so that each client gets the closing message.

The server protects the socket as follows:

* The socket file is created with the mode `0600`, with no moment where another
  user could connect.
* The folder of the socket must belong to the user running the server (or to
  root) and must not be writable by others, unless it has the sticky bit (like
  `/tmp`): another user could replace the socket. Prefer a private folder, like
  `$XDG_RUNTIME_DIR`.
* A socket file left by a server which was not stopped properly is replaced,
  never a regular file, a symbolic link or the socket of a running server. The
  file is removed at stop, unless it was replaced in the meantime.
* Where the system tells it (`SO_PEERCRED`, on Linux), a client run by another
  user than the server (root excepted) is disconnected, unless
  `pelix.shell.unix.check_peer` is false.
* The TLS properties are refused rather than ignored, so that nobody believes
  that clients are authenticated by certificate.

A client of the socket runs as the user the system tells (see
[](#authentication-and-authorization)): it is trusted like the console, with no
login and no permission check, as it could run the framework itself. Where the
system can't tell, or when `pelix.shell.unix.check_peer` is false, the client must
log in with a password, as on TCP.

Unix sockets are only supported on Linux and macOS.

:::{versionadded} 3.3.0
The `pelix.shell.unix.path` and `pelix.shell.unix.check_peer` properties and
the `--unix` argument.
:::

#### Remote shell authentication

The remote shell identifies its users through the security layer described in
{doc}`security`. It needs the `pelix.security.core` bundle (started by the
`pelix.shell.remote` script), plus at least one credential store: typically
`pelix.security.htpasswd` for passwords and `pelix.security.policy` for certificates,
groups, roles and permissions. Without them, nobody can log in over TCP.

A TCP client is authenticated when it connects, before it can run anything:

1. **With its TLS client certificate.** On a TLS connection, the certificate the
   client presented, already verified against `pelix.shell.ssl.ca`, is mapped to a
   user by the `[certificates]` tables of the policy file. A mapped certificate opens
   the session as that user, without any prompt.
2. **With a login and a password** otherwise, including with a valid certificate
   mapped to no user. The shell prompts `Login:` and `Password:`, and closes the
   connection after 3 failed attempts.

Nothing runs before a successful login: not even `help`. Whatever is written at the
`Login:` prompt is a user name, never a command.

```toml
# The policy file: certificates mapped to users, and what those users may do
[certificates.fingerprints]
"3F:5A:...:E9" = "thomas"

[roles.admin]
users = ["thomas"]

[permissions]
admin = ["pelix.shell.admin", "pelix.shell.debug"]
```

The `pelix.shell.ssl.client_auth` property sets what a certificate is for:

* `required` (default): every client presents a certificate signed by
  `pelix.shell.ssl.ca`, mapped or not. The others fail the TLS handshake.
* `optional`: a certificate a client presents must be signed by
  `pelix.shell.ssl.ca`, but a client may present none, and then logs in with a
  password over TLS.
* `none`: no certificate is asked, and every client logs in with a password over TLS.
  `pelix.shell.ssl.ca` must not be set.

:::{warning}
**Certificates are the recommended way to log in.** A password typed in a basic client
like `nc` or `telnet` is **echoed** on the screen, like any other input. With the
`optional` and `none` modes, TLS only protects a password if the client verifies the
certificate of the server, which the server can't enforce: use a client which does,
like `openssl s_client -verify_return_error -CAfile ca.crt -connect host:9000` or
`socat - OPENSSL:host:9000,cafile=ca.crt,verify=1`.
:::

The client address is given to the security layer as the source of a password attempt,
so that its brute-force throttling (see {doc}`security`) locks out both an account and
a client address which fail too often. A locked-out account gets the same `Login
incorrect` answer as a wrong password. A certificate mapped to no user only counts
against itself, not against its address: the TLS layer verified it, so it is no guess.

Each command line is logged at the `INFO` level with the user, the client address and
the command name, as in `User thomas from 10.0.0.1 requested ipopo.instances`, but
without its arguments, which may hold secrets. The full line is only logged at the
`DEBUG` level. A refused command is logged at the `WARNING` level.

When an error happens outside of a command, its stack trace is sent to the client only
if the subject of the session is granted the `pelix.shell.debug` permission. Other
clients get an error ID, which the log associates with the stack trace.

### XMPP Shell

The XMPP shell interface allows to communicate with a Pelix framework
using an XMPP client, e.g. [Pidgin](https://pidgin.im/),
[Psi](https://psi-im.org/). The biggest advantages of this interface are
the possibility to use TLS to encrypt conversations and the fact that it
is an output-only communication. This allows to protect Pelix
applications behind hardened firewalls, letting them only to connect the
XMPP server.

It requires an XMPP account to connect an XMPP server. Early tests of
this bundle were made against Google Talk (with a GMail account, not to
be confused with Google Hangout) and a private
[OpenFire](https://www.igniterealtime.org/projects/openfire/) server.

#### Script startup

The XMPP UI can be started using the `python -m pelix.shell.xmpp`
command. This command will start a Pelix framework with iPOPO, and will
start a Pelix console UI locally.

In addition to the common parameters, the script accepts the following ones:

| Argument | Default | Description |
|----|----|----|
| `-j JID`, `--jid JID` | `None` | Jabber ID (user account) |
| `--password PASSWORD` | `None` | Account password |
| `-s ADDR`, `--server ADDR` | `None` | Address of the XMPP server (found in the Jabber ID by default) |
| `-p PORT`, `--port PORT` | 5222 | Port of the XMPP server |
| `--no-tls` | *not set* | If set, don't use a STARTTLS connection |
| `--ssl` | *not set* | If set, use an SSL connection |
| `--no-tls-verify` | *not set* | If set, don't verify the certificate of the XMPP server |
| `-u JID=NAME`, `--user JID=NAME` | *none* | Allow this JID to use the shell, as this user of the security layer (repeatable) |

#### Programmatic startup

This UI depends on the `slixmpp` third-party package, which can be
installed using the following command:

```bash
pip install slixmpp
```

The XMPP shell is provided as the `ipopo-xmpp-shell-factory` component
factory defined in the `pelix.shell.xmpp` bundle. You should use the
constant `pelix.shell.FACTORY_XMPP_SHELL` instead of the factory name
when instantiating the component.

This factory accepts the following properties:

| Name                  | Default   | Description               |
|-----------------------|-----------|---------------------------|
| `shell.xmpp.server`   | localhost | XMPP server hostname      |
| `shell.xmpp.port`     | 5222      | XMPP server port          |
| `shell.xmpp.jid`      | `None`    | JID (XMPP account) to use |
| `shell.xmpp.password` | `None`    | User password             |
| `shell.xmpp.tls`      | 1         | Use a STARTTLS connection |
| `shell.xmpp.ssl`      | 0         | Use an SSL connection     |
| `shell.xmpp.tls.verify` | 1       | Verify the certificate of the XMPP server |
| `shell.xmpp.users`    | `None`    | Who may use the shell: a dictionary associating a bare JID to a user name of the security layer |
| `shell.xmpp.idle_timeout` | 3600  | Seconds a session waits for a command, or for the answer to a command asking for input, before it ends. `0` removes the limit |
| `shell.xmpp.max_sessions` | 4     | Maximum number of simultaneous sessions of a JID (one per resource), so that a user can't take the sessions of the others. `0` removes the limit |

The shell answers only the JIDs of `shell.xmpp.users`, whatever their resource: any
other message is ignored, as are the messages of the bot account itself, those of a
group chat, and those the server delivers late (kept while the bot was offline, or
forwarded), which may come from someone who has since lost the right to send them. The
XMPP server authenticates the sender: the shell trusts it, and the servers it federates
with, to tell who sent a message. Each command runs as the user name of its sender,
with the groups and roles the security layer gives it, and only if that user holds the
permission of the command (see [](#authentication-and-authorization)). Only the users
of the shell can subscribe to the presence of the bot, which gives them no other access.
The subscription of a JID removed from `shell.xmpp.users` is revoked when the bot
connects, at the next presence it receives, or at the next message of a JID which is
not a user.

Each session (one per full JID) runs its commands in its own thread, in the order they
were sent: a command waiting for an answer only blocks its own session. Without an
answer within `shell.xmpp.idle_timeout`, the command reads an end of input, and a
session without commands for that long ends. When a user accepts the subscription of
the bot to its presence, its session also ends as soon as its client goes offline.

:::{versionchanged} 3.3.0
The `shell.xmpp.users`, `shell.xmpp.idle_timeout` and `shell.xmpp.max_sessions`
properties and the `--user` argument. Before, the XMPP shell answered anyone who could
send a message to its account, and ran all the commands in a single thread.
:::

:::{warning}
`shell.xmpp.tls.verify` defaults to `1` since iPOPO 3.3.0 (it was `0` before).
Setting it to `0` disables the verification of the certificate of the XMPP
server: an attacker able to intercept the connection can then impersonate the
server and capture the credentials of the shell account.
:::

## Authentication and authorization

A shell session is either **trusted** or not:

* The console and the clients of a remote shell Unix socket (where the system tells
  who they are) are trusted. They run as the user of the operating system, read from
  the account database (never from the `USER` environment variable), and no permission
  is checked: they could run the framework with the same rights anyway.
* Every other session, a TCP or XMPP client, or a line given to
  `ShellService.execute()` without a session, needs the permission of each command it
  runs, from the security layer (see {doc}`security`). Without the `pelix.security.core`
  bundle, or without an authorizer, such a session can run nothing but `exit`.

Each command declares the permission it requires:

| Permission | Commands |
|----|----|
| `pelix.shell.read` | The listings and details of bundles, services and components (`bl`, `bd`, `sl`, `sd`, `ipopo.factories`, `ipopo.instances`, ...), `help`, `echo`, `set`, `unset`, `pwd`, `whoami` |
| `pelix.shell.admin` | Every command, including all those which declare nothing, such as the commands of third-party bundles |

`pelix.shell.admin` is not a finer level than full control: installing a bundle,
instantiating a component, running a script or changing a configuration all execute
arbitrary code as the user of the process. The `pelix.shell.read` level excludes the
commands which show secrets, like the framework properties, the environment variables,
the stacks of the threads (with their local variables), the configurations and the
reports.
It does show the properties of services and components (`sd`, `ipopo.instance`):
a component must declare a secret with `@HiddenProperty`, never with `@Property`.

In a session which is not trusted:

* the permission is checked for each command, including those of a script run by
  `run`, with the groups and roles of the user read again, so that a removal applies at
  once;
* a refused command gets the same answer as an unknown one, and `help` only lists the
  commands the session can run;
* `$name` is replaced by the session variables only, never by the framework properties,
  which may hold secrets;
* the error of a command only shows its details with the `pelix.shell.debug`
  permission; otherwise the client gets an error ID, which the log associates with the
  stack trace.

A command provider declares the permission of a command with the
`pelix.shell.CommandPermission` decorator, on the command method:

```python
from pelix.shell import PERMISSION_READ, CommandPermission


@CommandPermission(PERMISSION_READ)
def list_jobs(self, session: ShellSession) -> None: ...
```

Any {class}`~pelix.security.Permission` can be declared: `pelix.shell.admin` always
suffices. `CommandPermission(None)` makes a command anyone can run, which only makes
sense for a command like `exit`.

:::{versionadded} 3.3.0
The permissions of the shell commands and the trusted sessions. Before, a remote
client could run any command once logged in, or anonymously.
:::

## Provided command bundles

Pelix/iPOPO comes with some batteries included. Here is the list of the
bundles which provide commands for specific services.

Note that the commands themselves won't be described here: it is
recommended to use the `help` command in the shell to have the latest
usage information.

| Bundle name | Description |
|----|----|
| `pelix.shell.ipopo` | Handles iPOPO factories and instances. |
| `pelix.shell.configadmin` | Handles the Configuration Admin service (provided by `pelix.services.configadmin`). See [](./configadmin.rst). |
| `pelix.shell.eventadmin` | Handles the Event Admin service (provided by `pelix.services.eventadmin`). See [](./eventadmin.rst). |
| `pelix.shell.log` | Looks into the Log Service (provided by `pelix.misc.log`). See [](./log.rst). |
| `pelix.shell.report` | Generates framework state reports. See [](./shell_report.md). |

## How to provide commands

### Shell Command service

Shell commands are detected by the Shell Core Service when a Shell
Command service ([`pelix.shell.ShellCommandsProvider`](#pelix.shell.ShellCommandsProvider))
is registered.

First, the Shell Core calls the `get_namespace()` method of the new
service, in order to prepare the (potentially new) command namespace.
Each shell command provider **should** have a unique, human-readable,
namespace. Sometimes it can be interesting to have multiple services
providing sets of optional commands in the same namespace, but this can
lead to some unexpected behaviour, *e.g.* when trying to provide the
same command name twice in the same namespace. A namespace must not
contain spaces nor separator characters (dot, comma, ...).

Then, the Shell Core calls `get_methods()`, which must a return a list
of (command name, command method) couples. Like its namespace, a command
name must not contain spaces nor separator characters (dot, comma, ...).

Each command method must accept at least one argument: the
[`pelix.shell.beans.ShellSession`](#pelix.shell.beans.ShellSession) object
representing the current session and handling interactions with the client.
Note that the Python *docstring* of the method will be what is shown by the
core *help* command.

The shell core bundle also provides a utility service,
[`pelix.shell.ShellUtils`](#pelix.shell.ShellUtils), which
can be used to generate ASCII tables to print out to the user. This is
the service used by the core method to print the list of bundles,
services, iPOPO instances, etc.

Here is an example of a simple command service providing the *echo* and
*hello* shell commands. *echo* accepts an unlimited list of arguments
and prints it back to the client. *hello* asks a name if it wasn't given
as parameter then says hello.

```python
from pelix.ipopo.decorators import ComponentFactory, Provides, Instantiate
import pelix.shell
from pelix.shell.beans import ShellSession


@ComponentFactory("sample-commands-factory")
@Provides(pelix.shell.ShellCommandsProvider)
@Instantiate("sample-shell-commands")
class SampleCommands(pelix.shell.ShellCommandsProvider):
    """
    Sample shell commands
    """

    def get_namespace(self):
        """
        Retrieves the name space of this command handler
        """
        return "sample"

    def get_methods(self):
        """
        Retrieves the list of tuples (command, method) for this command handler
        """
        return [("echo", self.echo), ("hello", self.hello)]

    def hello(self, session: ShellSession, name: str | None = None) -> None:
        """
        Says hello
        """
        if not name:
            # Name not given as parameter, ask for it
            name = session.prompt("What's your name? ")

        session.write_line("Hello, {0} !", name)

    def echo(self, session: ShellSession, *words: str) -> None:
        """
        Prints back the words it has been given
        """
        session.write_line(" ".join(words))
```

To use this sample, simply start a framework with the Shell Core, a
Shell UI and iPOPO, then install and start the sample bundle. For
example:

```
bash:~ $ python -m pelix.shell
** Pelix Shell prompt **
$ start pelix.shell.toto
Bundle ID: 14
Starting bundle 14 (pelix.shell.toto)...
$ sample.echo Hello, world !
Hello, world !
$ hello World
Hello, World !
$ hello
What's your name? Thomas
Hello, Thomas !
```

The I/O handling of the `session` argument is implemented by the shell
UI and hides the ways used to communicate with the client. The code of
this example works with all UIs: local text UI, remote shell and XMPP
shell.

### API

```{eval-rst}
.. autoclass:: pelix.shell.beans.ShellSession
   :members:

   .. note:: This class is instantiated by Shell UI implementations and its
             instances shouldn't be shared nor stored by command providers.

.. autoclass:: pelix.shell.ShellUtils
   :members:

   .. note:: This class shouldn't be instantiated directly and should be used
             as a service.

.. autoclass:: pelix.shell.ShellCommandsProvider
   :members:
```

## How to prepare certificates for the Remote Shell

In order to use certificate-based client authentication with the Remote
Shell in TLS mode, you will have to prepare a certificate authority,
which will be used to sign server and clients certificates.

The following commands are a summary of
[OpenSSL Certificate Authority](https://jamielinux.com/docs/openssl-certificate-authority/index.html)
page by [Jamie Nguyen](https://jamielinux.com/).

### Prepare the root certificate

* Prepare the environment of the root certificate:

  ```bash
  mkdir ca
  cd ca/
  mkdir certs crl newcerts private
  chmod 700 private/
  touch index.txt
  echo 1000 > serial
  ```

* Download the sample
  [openssl.cnf](https://jamielinux.com/docs/openssl-certificate-authority/appendix/root-configuration-file.html)
  file to the `ca/` directory and edit it to fit your needs.

* Create the root certificate. The following snippet creates a 4096 bits
  private key and creates a certificate valid for 7300 days (20 years).
  The `v3_ca` extension allows to use the certificate as an authority.

  ```bash
  openssl genrsa -aes256 -out private/ca.key.pem 4096
  chmod 400 private/ca.key.pem

  openssl req -config openssl.cnf -key private/ca.key.pem \
      -new -x509 -days 7300 -sha256 -extensions v3_ca \
      -out certs/ca.cert.pem
  chmod 444 certs/ca.cert.pem

  openssl x509 -noout -text -in certs/ca.cert.pem
  ```

### Prepare an intermediate certificate

Using intermediate certificates allows to hide the root certificate
private key from the network: once the intermediate certificate has
signed, the root certificate private key should be hidden in a server
somewhere not accessible from the outside. If your intermediate
certificate is compromised, you can use the root certificate to revoke it.

* Prepare the environment of the intermediate certificate:

  ```bash
  mkdir intermediate
  cd intermediate/
  mkdir certs crl csr newcerts private
  chmod 700 private/
  touch index.txt
  echo 1000 > serial
  echo 1000 > crlnumber
  ```

* Download the sample
  [intermediate/openssl.cnf](https://jamielinux.com/docs/openssl-certificate-authority/appendix/intermediate-configuration-file.html)
  file to the `ca/intermediate` folder and edit it to your needs.

* Generate the intermediate certificate and sign it with the root
  certificate. The `v3_intermediate_ca` extension allows to use the
  certificate as an intermediate authority. Intermediate certificates
  are valid less time than the root certificate. Here we consider a
  validity of 10 years.

  ```bash
  openssl genrsa -aes256 -out intermediate/private/intermediate.key.pem 4096
  chmod 400 intermediate/private/intermediate.key.pem

  openssl req -config intermediate/openssl.cnf \
      -new -sha256 -key intermediate/private/intermediate.key.pem \
      -out intermediate/csr/intermediate.csr.pem

  openssl ca -config openssl.cnf -extensions v3_intermediate_ca \
      -days 3650 -notext -md sha256 \
      -in intermediate/csr/intermediate.csr.pem \
      -out intermediate/certs/intermediate.cert.pem
  chmod 444 intermediate/certs/intermediate.cert.pem

  openssl x509 -noout -text -in intermediate/certs/intermediate.cert.pem

  openssl verify -CAfile certs/ca.cert.pem \
      intermediate/certs/intermediate.cert.pem
  ```

* Generate the Certificate Authority chain file. This is simply the
  bottom list of certificates of your authority:

  ```bash
  cat intermediate/certs/intermediate.cert.pem certs/ca.cert.pem \
      > intermediate/certs/ca-chain.cert.pem

  chmod 444 intermediate/certs/ca-chain.cert.pem
  ```

### Prepare the server certificate

The steps to generate the certificate is simple. For simplicity, we
consider we are in the same folder hierarchy as before.

This certificate must has a validity period shorter than the
intermediate certificate.

1.  Generate a server private key. This can be done on any machine:

    ```bash
    openssl genrsa -aes256 -out intermediate/private/server.key.pem 2048
    openssl genrsa -out intermediate/private/server.key.pem 2048
    chmod 400 intermediate/private/server.key.pem
    ```

2.  Prepare a certificate signing request

    ```bash
    openssl req -config intermediate/openssl.cnf \
        -key intermediate/private/server.key.pem -new -sha256 \
        -out intermediate/csr/server.csr.pem
    ```

3.  Sign the certificate with the intermediate certificate. The
    `server_cert` extension indicates a server certificate which can't
    sign other ones.

    ```bash
    openssl ca -config intermediate/openssl.cnf -extensions server_cert \
        -days 375 -notext -md sha256 \
        -in intermediate/csr/server.csr.pem \
        -out intermediate/certs/server.cert.pem
    chmod 444 intermediate/certs/server.cert.pem

    openssl x509 -noout -text -in intermediate/certs/server.cert.pem

    openssl verify -CAfile intermediate/certs/ca-chain.cert.pem \
        intermediate/certs/server.cert.pem
    ```

### Prepare a client certificate

The steps to generate the client certificates are the same as for the
server.

1.  Generate a client private key. This can be done on any machine:

    ```bash
    openssl genrsa -out intermediate/private/client1.key.pem 2048
    chmod 400 intermediate/private/client1.key.pem
    ```

2.  Prepare a certificate signing request

    ```bash
    openssl req -config intermediate/openssl.cnf \
        -key intermediate/private/client1.key.pem -new -sha256 \
        -out intermediate/csr/client1.csr.pem
    ```

3.  Sign the certificate with the intermediate certificate. The
    `usr_cert` extension indicates this is a client certificate, which
    cannot be used to sign other certificates.

    ```bash
    openssl ca -config intermediate/openssl.cnf -extensions usr_cert \
        -days 375 -notext -md sha256 \
        -in intermediate/csr/client1.csr.pem \
        -out intermediate/certs/client1.cert.pem
    chmod 444 intermediate/certs/client1.cert.pem

    openssl x509 -noout -text -in intermediate/certs/client1.cert.pem

    openssl verify -CAfile intermediate/certs/ca-chain.cert.pem \
        intermediate/certs/client1.cert.pem
    ```

## Connect a TLS Remote Shell

To connect a basic remote shell, you can use `netcat`, which is
available for nearly all operating systems and all architectures.

To connect a TLS remote shell, you should use the OpenSSL client:
`s_client`. It is necessary to indicate the client certificate in order
to be accepted by the server. It is also recommended to indicate the
authority chain to ensure that the server is not a rogue one.

Here is a sample command line to connect a TLS remote shell on the local
host, listening on port 9001.

```bash
openssl s_client -connect localhost:9001 \
    -cert client1.cert.pem -key client1.key.pem \
    -CAfile ca-chain.cert.pem
```
