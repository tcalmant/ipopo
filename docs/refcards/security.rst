.. _refcard_security:
.. module:: pelix.security

Authentication and Authorization
################################

.. versionadded:: 3.2.3

Pelix provides an authentication and authorization layer: who is calling, which
groups and roles they hold, and what they may do. It is transport-neutral, so the
same credential store serves an HTTP request, a shell login or a message broker
connection.

What this layer does not do
===========================

**Pelix has no code-level permission model.** There is no equivalent of OSGi's
``ConditionalPermissionAdmin``, no sandbox and no signed-bundle verification. Any
bundle which gets installed can register a higher-ranked :class:`Authorizer` and take
over every decision described below, or simply ``import pelix.security`` and call
:func:`run_as`.

This layer therefore protects against **remote callers, not against locally installed
bundles**. Read every guarantee below with that boundary in mind.

Four questions, four services
=============================

============================================== ============================== ==========================
Question                                       Service                        Shipped implementation
============================================== ============================== ==========================
How do I get credentials off this transport?   (transport-specific)           HTTP: :ref:`http_auth`     
Are these credentials valid, and who is it?    :class:`Authenticator`         ``.htpasswd``, policy file
Which groups and roles does this subject have? :class:`MembershipProvider`    ``.htgroup``, policy file
May this subject do this?                      :class:`Authorizer`            policy file
============================================== ============================== ==========================

Plus exactly one facade, :class:`Authorization`, which is what application code
injects or reaches through :func:`use_authorization`.

The remote services use this layer to authorize the calls to the exported services,
with the ``pelix.remote.call`` permission, and to send credentials to their peers: see
:ref:`remote_services_security`.

Bundles
=======

============================= =============================================================
Bundle                        What it brings
============================= =============================================================
``pelix.security.core``       ``authenticate()``, the :class:`Authorization` facade
``pelix.security.htpasswd``   an :class:`Authenticator` and a :class:`MembershipProvider`
``pelix.security.policy``     roles from groups, permissions from roles, certificates to
                              users, and the escape hatch
``pelix.security.audit``      optional: writes the security events and the reveals of
                              secrets to the ``pelix.security.audit`` logger
============================= =============================================================

:mod:`pelix.security` itself, holding the beans and the current subject, needs no
bundle at all: it imports the standard library and :mod:`pelix.constants`, and nothing
else.

The subject
===========

A :class:`Subject` is a complete, immutable snapshot of who is calling: a person, a
service account, a device, a peer framework, or the anonymous caller. It carries three
flat levels:

* ``name`` is the user;
* ``groups`` is the membership an identity source asserted;
* ``roles`` is the entitlement level a policy granted from those facts.

There is no membership graph, no nesting and no ``Role`` object. All three levels are
resolved once, when the subject is authenticated, so a queued execution path carries
its identity with it and needs no service call at the far end. The price is stated
next to the benefit: a membership change reaches a caller at their next
authentication, not immediately.

Where the transport knows it, the subject also tells where the request came from:

* ``peer_address`` is the other end of the connection, a reverse proxy if there is one;
* ``client_address`` is the client, as told by the ``X-Forwarded-For`` header of the
  trusted proxies only (``pelix.http.proxy.trusted``, see :doc:`http`), the peer address
  otherwise. It is only as reliable as those proxies.

The HTTP services set both on every request, the anonymous ones included, and the
remote shell sets both to the address of its TCP client (``whoami`` shows them). They
are ignored when comparing subjects: where a request comes from doesn't change who the
caller is.

.. versionadded:: 3.3.0
   The ``peer_address`` and ``client_address`` fields.

Identifiers are compared exactly
--------------------------------

**This layer folds nothing.** No ``lower()``, no ``casefold()``, no Unicode
normalization, for user names, group names, role names or permission actions,
anywhere.

The first reason is conformance: the identifiers this layer handles are defined as
case-sensitive by the specifications which issue them, from the OpenID Connect ``sub``
claim to OAuth 2.0 scope tokens. The second is that folding can only fail unsafely:
these are allow-lists, so a match which should not have happened **grants** access,
and every folding scheme widens the set of strings mapping onto a privileged name.

Folding belongs to whoever owns the matching rule. A provider sitting on a source
which really is case-insensitive, such as an LDAP directory, applies that rule itself
and documents the single canonical form it emits.

The cost is direct: a name has to be spelled identically in the identity source, in
the policy file and in the decorators. ``Dev`` from a directory against ``dev`` in a
policy file denies, silently, and presents as a policy bug rather than as the data bug
it is. When a check denies inexplicably, look at the spelling before looking at the
logic; the policy loader reports the two shapes such a typo usually takes.

The current subject
===================

The caller is carried in a :class:`contextvars.ContextVar`, and the rule is a
framework-wide one rather than a security feature:

    **The current subject follows the standard Python context.** Wherever a Python
    context propagates, the subject propagates; wherever it does not, the subject does
    not, and the code crossing that boundary copies the context explicitly.

.. autofunction:: get_current_subject

.. autofunction:: run_as

Both are plain module functions, with no service and no bundle required. The asymmetry
is deliberate: *authorization* needs policy, and therefore a service; *identity* is a
fact, and it is free. It is also what makes the layer testable::

    with run_as(Subject("alice", roles=frozenset({"admin"}), authenticated=True)):
        obj.do_the_thing()

No framework, no bundle, no mock.

:class:`~pelix.threadpool.ThreadPool` and the asynchronous HTTP service both carry the
context across their thread boundaries, so a subject published before a task is queued
is visible inside it.

Permissions
===========

A :class:`Permission` is an action, optionally scoped to a resource:
``jobs.submit``, ``jobs.submit:queue-a``. Strings are parsed at the edges, once, so a
single type flows through the services.

The matching rule is small and complete. An action matches in one of three ways:

=============== =============================================================
Grant action    Matches
=============== =============================================================
``jobs.submit`` exactly ``jobs.submit``
``jobs.*``      every action starting with ``jobs.``, at any depth, but not
                ``jobs`` itself
``*``           every action. The only all-grant form
=============== =============================================================

And a resource in one of four:

================ ===================== ==============================================
Grant resource   Request resource      Result
================ ===================== ==============================================
absent           anything              match: the grant is not resource-scoped
``*``            anything              match
``queue-a``      ``queue-a``           match
``queue-a``      absent, or any other  no match
================ ===================== ==============================================

A grant scoped to a resource therefore never satisfies a request naming none:
``jobs.submit:queue-a`` does not imply ``jobs.submit``. That is the safe direction.

Decorators
==========

Read every one of them as **"allow only"**: ``@AllowGroup("dev")`` means "allow only
the dev group". Each decorator narrows who can reach the target, and the names listed
inside one decorator are alternatives::

    @AllowAuthenticated                  # allow only authenticated subjects
    @AllowGroup("dev", "ops")            # allow only these groups (any of them)
    @AllowRole("admin")                  # allow only these roles (any of them)
    @AllowPermission("jobs.submit")      # parsed once, at decoration time
    @AllowAll                            # no narrowing: overrides a class-level default
    @DenyAll                             # total narrowing
    @RunAs(Subject("batch", roles=frozenset({"operator"})))

The rule follows from that reading: **any-of within one decorator, all-of when they
are stacked, and a method-level declaration replaces a class-level one entirely.**
Stacking ``@AllowGroup("dev")`` and ``@AllowRole("admin")`` therefore means "only
members of ``dev`` who also hold ``admin``".

``@AllowAuthenticated``, ``@AllowAll`` and ``@DenyAll`` take no argument and are
written bare, without parentheses. The others always take at least one. No decorator
supports both forms, and applying an argument-taking one bare raises ``TypeError`` at
import time.

Applied to a class, a decorator sets the default of every function defined **in that
class body** whose name does not start with an underscore. It does not reach inherited
methods, and a method which carries its own declaration keeps it.

There is no ``@AllowUser``. Deployment configuration may legitimately name a user;
source code should not.

What a refusal raises
---------------------

The choice between the two exceptions is mechanical:

* the current subject is **not authenticated**: :class:`AuthenticationRequired`. Over
  HTTP this becomes a 401 with a challenge, so a client can retry with credentials;
* the current subject **is authenticated** but does not satisfy the declaration:
  :class:`AccessDenied`, which becomes a 403. Retrying with the same credentials is
  pointless and the status says so.

``@DenyAll`` always raises the second, even for an anonymous subject: no credential
would help, so offering a challenge would be a lie.

``@RunAs`` is privilege escalation by construction: anyone who can import it can
elevate. In a framework with no sandbox it is a readability tool, not a security
boundary. There is no built-in all-powerful subject, which keeps it at worst a lateral
move: a system identity is an ordinary ``Subject("system", roles=frozenset({"system"}))``
whose authority comes from the policy file.

Fail closed
-----------

================================================== ==========================================
Situation                                          Behaviour
================================================== ==========================================
``pelix.security.core`` not started                every decorator but ``@AllowPermission``
                                                   still works: they are pure context-variable
                                                   operations. ``@AllowPermission`` denies,
                                                   with one warning per distinct permission
Started, no :class:`Authorizer` registered         deny, with one warning
Genuinely permissive wanted                        instantiate
                                                   ``pelix.security.authorizer.allow-all.factory``,
                                                   which warns when it validates
================================================== ==========================================

You cannot become permissive by accident. State the consequence loudly in your own
documentation: **installing a library whose methods carry ``@AllowPermission``, and
not starting the bundle, means those methods raise.**

The pipeline
============

``pelix.security.core.authenticate(credentials, source=None, *, method=None, transport=None)`` turns
credentials into a subject:

1. every :class:`Authenticator` accepting this kind of credentials is consulted in
   ``service.ranking`` order;
2. every :class:`MembershipProvider` contributes groups, and the results are unioned;
3. the subject is rebuilt with those groups, and only then does every provider
   contribute roles;
4. the subject is returned, authenticated, with ``method`` and ``transport`` set to
   the arguments the transport gave, or left unset for the transport to stamp later.

``method`` names the mechanism (``password``, ``certificate``, ``basic``, ...) and
``transport`` the way the request came in (``http``, ``shell``, ...). They are kept
apart because several transports can use the same mechanism, and an audit has to tell
a login to an administration shell from a call to a service.

Step 3 is two passes rather than one, and that is load-bearing: it is what lets the
policy file grant a role from a group a *different* provider asserted. With a single
pass the policy would look at a subject whose groups are still empty and answer
nothing.

An :class:`Authenticator` tells *who* the subject is, and nothing more: groups and
roles come from the :class:`MembershipProvider` services. Those an authenticator puts
in the subject it returns are kept for that authentication, with a warning, but
``restore_subject()`` only asks the providers: they are lost from the next request of an
HTTP session, or the next command of a shell.

The three-state authenticator contract
--------------------------------------

This is the most important detail of the pipeline. Two outcomes are not enough:

* returning a :class:`Subject` means success: stop;
* returning ``None`` means **abstain**: not my credential kind, not my user, try the
  next one;
* raising :class:`AuthenticationFailed` means **presented and wrong**: stop, and do
  not consult lower-ranked authenticators.

Without the third state, a low-ranked fallback store silently becomes an oracle for
credentials a higher-ranked store already rejected: user ``admin`` exists in the main
store with one password and in an emergency ``.htpasswd`` with another, and the second
one keeps working forever.

An :class:`Authenticator` must declare the credential kinds it accepts, in its
``pelix.security.credentials`` service property. One which does not is never
consulted.

Brute-force throttling
----------------------

``authenticate(credentials, source=None)`` counts its failures, and refuses the
credentials of a key which failed too often **without consulting any
authenticator**. Two keys are tracked for each attempt:

* the **account**: the credential kind and the user name for a password, the
  fingerprint for a certificate. Credentials naming no account have no account key;
* the **source**, when the transport gives one in the ``source`` argument, typically
  the client IP address.

After ``max_failures`` failures of a key within ``window`` seconds, that key is locked
out for ``lockout`` seconds. The count is a sliding window: once a lockout is over, one
more failure within the window locks the key out again, for twice as long, up to
``max_lockout`` seconds. A key which stayed quiet for a whole window starts again from
scratch. A successful authentication clears the failures of its account, never those
of its source: a source which guessed one password right is not forgiven the failures
it made on other accounts.

A locked-out attempt raises the same :class:`AuthenticationFailed` as a wrong
password, so that a caller cannot use the lockout to learn that an account exists. A
``WARNING`` is logged once when a lockout starts, naming the key.

The throttle is configured with framework properties, read when the
``pelix.security.core`` bundle starts:

========================================= ======= ====================================
Framework property                        Default Meaning
========================================= ======= ====================================
``pelix.security.throttle.max_failures``  5       failures which lock a key out.
                                                  ``0`` or less disables the throttle
``pelix.security.throttle.window``        900     seconds within which failures count
``pelix.security.throttle.lockout``       60      seconds of the first lockout
``pelix.security.throttle.max_lockout``   900     upper bound of a lockout, in seconds
========================================= ======= ====================================

It lives in memory, in the framework process: a restart forgets it, and several
frameworks behind a load balancer each count on their own. It tracks at most 10000
keys and forgets the least recently touched one beyond that, so that a flood of
sources costs a bounded amount of memory; the price is that such a flood can make it
forget a key early.

**The trade-off.** Anybody who knows a user name can lock that account out, by failing
on purpose, and the legitimate user is then refused from every source until the
lockout ends. Two things limit the damage. The failures which lock an account also
count against the attacker's own source, so one source can only keep about one account
locked at a time, and gets locked out longer and longer while doing so. And a lockout
never exceeds ``max_lockout``, so the denial of service ends on its own. A deployment
which cannot accept it for an account should authenticate that account with a client
certificate, which cannot be guessed, rather than with a password.

The locked-out answer is also immediate, while a wrong password costs a hash
computation: timing tells a patient attacker that a key is locked, not whether its
password was right.

Combining authorizers
---------------------

One fixed, non-configurable rule: **any DENY denies; otherwise any PERMIT permits;
otherwise deny.** :attr:`Decision.ABSTAIN` is what lets independent policies compose.
An authorizer which raises denies: one which cannot decide has not decided.

The ``.htpasswd`` store
=======================

``pelix.security.htpasswd`` provides both an :class:`Authenticator` over a password
file and a :class:`MembershipProvider` over a matching ``.htgroup``.

============================================ =========================================
Property                                     Meaning
============================================ =========================================
``pelix.security.htpasswd.file``             path of the password file (mandatory)
``pelix.security.htpasswd.groups``           path of the group file
``pelix.security.htpasswd.allow_plaintext``  accept an unrecognized hash as a plaintext
                                             password. Default: ``False``
============================================ =========================================

Hash formats
------------

============================ ==========================================================
Format                       Support
============================ ==========================================================
``$5$``, ``$6$`` SHA-crypt   supported, and recommended. ``htpasswd -2``, ``htpasswd -5``
``$apr1$`` Apache MD5        supported. ``htpasswd -m``
``{SHA}`` base64 SHA-1       supported, with a warning: unsalted and unstretched
``$2a$``, ``$2b$``, ``$2y$`` bcrypt, when the optional ``iPOPO[bcrypt]`` extra is
                             installed
DES crypt (13 characters)    refused: eight-character truncation, twelve-bit salt
anything else                treated as a plaintext password, refused unless allowed
============================ ==========================================================

The ``rounds=`` parameter of a SHA-crypt hash is capped at 100000. The format allows
999999999, which one login would turn into minutes of CPU.

The whole file is parsed when it is loaded, not entry by entry at login. An entry this
build cannot verify is reported with its file and line number, and its user is left
**absent** rather than present and unverifiable: a load-time failure is found by the
operator at deploy time. A world-readable password file is reported too.

An unknown user is checked against a dummy hash before the store abstains, so that it
does not answer visibly faster than a known one. One residual leak cannot be closed
there and is worth knowing: with several stores registered, an unknown user is
consulted against every one of them while a known user stops at the first.

The policy file
===============

``pelix.security.policy`` reads a TOML file granting roles from users and groups, and
permissions to roles:

.. code-block:: toml

    [roles.admin]
    users  = ["thomas"]
    groups = ["dev-leads"]

    [roles.operator]
    groups = ["dev", "ops"]

    [permissions]
    admin    = ["jobs.*", "config.*"]
    operator = ["jobs.read", "jobs.submit"]

Its path is the ``pelix.security.policy.file`` property.

The format is TOML because **TOML keys are case-sensitive by specification**, and role
names are keys here: an INI file would have folded them in the very component which
must fold nothing. Typed tables also say whether a name is a user or a group in the
schema, and a duplicate key is a parse error rather than a silently kept last one.

Two things are reported when the file is loaded, and both are worth acting on:

* every grant containing a ``*``, naming the file and the role. A wildcard is one typo
  away from full access;
* every **dangling reference**: a role granted to somebody but never given a
  permission, and a permission granted to a role nobody holds. Most spelling mistakes
  produce one of those two shapes.

This authorizer never returns ``DENY``, only ``PERMIT`` or ``ABSTAIN``: the format
expresses grants only, so a policy file can never veto a permission another, looser
authorizer allows. There is no implicit all-grant either: an empty ``[permissions]``
table denies everything.

Client certificates
===================

A transport which authenticated its peer with a TLS client certificate, such as the
remote shell (see :doc:`shell`), turns it into :class:`ClientCertificate`
credentials, of kind ``certificate``:

* ``fingerprint``: the SHA-256 of the DER certificate, in lowercase hexadecimal with no
  separator;
* ``subject``: the subject, as an RFC 4514 style string, most specific name first:
  ``CN=batch,O=Acme,C=FR``;
* ``alt_names``: the subject alternative names, as ``type:value`` strings:
  ``DNS:batch.example.com``.

**These credentials must only be built from a certificate the TLS layer already
verified**, from a context requiring a client certificate signed by a trusted
authority. Nothing in this layer checks a signature, a validity period or a
revocation: the object says "the peer proved it holds this certificate", and an
authenticator only maps it to a user.

The policy file maps certificates to users in its ``[certificates]`` tables, which
makes its component an :class:`Authenticator` of ``certificate`` credentials:

.. code-block:: toml

    [certificates.fingerprints]
    "3F:5A:...:E9" = "thomas"

    [certificates.subjects]
    "CN=batch,O=Acme,C=FR" = "batch"

The groups and roles of the mapped user then come from the usual membership providers,
exactly as after a password login: a ``.htgroup`` file, the ``[roles]`` of the policy.

The two tables do not give the same guarantee:

* a **fingerprint** names this very certificate, whoever issued it. It is written as
  ``openssl x509 -noout -fingerprint -sha256 -in client.crt`` prints it, or in lowercase,
  with or without the ``:`` separators. Anything which is not a SHA-256 fingerprint,
  such as the SHA-1 one many tools print by default, refuses the file;
* a **subject** names whatever any trusted authority chose to issue under that name. It
  is only as strong as the *least careful* authority the transport trusts, so map
  subjects only behind a dedicated authority. It is compared exactly, like every other
  name of this layer: ``CN=batch, O=Acme`` with spaces is another string.

When a certificate matches both tables, the fingerprint wins. An unmapped certificate
abstains rather than fails: it passed the TLS verification, so it is not "presented and
wrong", and another :class:`Authenticator` may know it. The ``[certificates]`` tables
are validated as strictly as the rest of the file: an unknown key, a user name which is
not a non-empty string, or the same fingerprint written twice refuses the file.

Audit events
============

When an EventAdmin service is registered (see :doc:`eventadmin`), the
``pelix.security.core`` bundle posts an event for every authentication and every
refusal:

=================================== ======================================================
Topic                               Posted when
=================================== ======================================================
``pelix/security/AUTH_SUCCESS``     ``authenticate()`` returned a subject
``pelix/security/AUTH_FAILURE``     ``authenticate()`` raised :class:`AuthenticationFailed`
``pelix/security/ACCESS_DENIED``    ``Authorization.check_permitted()`` or a decorator
                                    refused a subject
=================================== ======================================================

The properties of the two authentication events:

================= ==================================================================
Property          Value
================= ==================================================================
``user``          the name of the authenticated subject on success; on failure, the
                  user name a password tried, ``None`` for other credentials
``kind``          the credential kind: ``password``, ``certificate``, ...
``method``        the ``method`` argument of ``authenticate()``, or ``None``
``transport``     the ``transport`` argument of ``authenticate()``, or ``None``
``source``        the ``source`` argument of ``authenticate()``, or ``None``
``reason``        failures only: ``rejected`` for wrong or unknown credentials,
                  ``throttled`` for a locked-out key
================= ==================================================================

And those of an access denied event: ``user`` and ``authenticated``, from the refused
subject, plus ``permission`` (the refused permission, as a string) and ``declaration``
(the decorator which refused it, such as ``AllowGroup('dev',)``) when they apply.

**No event ever holds a secret**: neither a password nor any other part of the
credentials but the user name. The failure reason is deliberately generic, like the
exception a caller gets. Keep in mind that a user name field sometimes receives a
password typed one line too early.

``Authorization.is_permitted()`` posts nothing: a question is not a refusal, and a
page asking about ten menu entries must not report ten denials. Neither does
``@AllowPermission`` with the ``pelix.security.core`` bundle stopped, since there is
then nothing to post through.

The events are posted asynchronously, and the EventAdmin service is looked up at each
event: it may come and go. An event which cannot be posted is logged and dropped. The
audit trail is never a condition of the decision: a missing or broken EventAdmin
changes neither an authentication nor an authorization.

Reloading
=========

Both bundles register as File Install listeners (see :doc:`fileinstall`), so writing
the file is enough. Without that bundle the files are read once at validation, which
is graceful degradation rather than a failure.

Two caveats come with it. File Install watches a **whole folder**, so the password
file belongs in its own directory. And on a parse failure, a shape failure, an empty
file or an unreadable one, **the previous table is kept** and an error is logged: an
empty file is far more likely a partial write than an intentional revocation of
everyone. A successfully parsed file with a user removed does revoke that user.

Worked example
==============

``/etc/pelix/auth/.htpasswd``, in its own directory:

.. code-block:: text

    thomas:$6$rounds=10000$FGkY6bLp$1qE...

``/etc/pelix/auth/.htgroup``:

.. code-block:: text

    # groupname: user1 user2
    dev-leads: thomas

``/etc/pelix/auth/policy.toml``:

.. code-block:: toml

    [roles.admin]
    groups = ["dev-leads"]

    [permissions]
    admin = ["jobs.*"]

The ``.ipopo`` initialization file (see :doc:`init_config`):

.. code-block:: json

    {
      "bundles": [
        "pelix.ipopo.core",
        "pelix.services.fileinstall",
        "pelix.security.core",
        "pelix.security.htpasswd",
        "pelix.security.policy"
      ],
      "components": [
        {"factory": "pelix.security.htpasswd.factory", "name": "users",
         "properties": {"pelix.security.htpasswd.file": "/etc/pelix/auth/.htpasswd",
                        "pelix.security.htpasswd.groups": "/etc/pelix/auth/.htgroup"}},
        {"factory": "pelix.security.policy.file.factory", "name": "policy",
         "properties": {"pelix.security.policy.file": "/etc/pelix/auth/policy.toml"}}
      ]
    }

And, in a component::

    import pelix.security.core
    from pelix.security import UsernamePassword, run_as
    from pelix.security.decorators import AllowPermission

    @AllowPermission("jobs.submit")
    def submit_job(name):
        ...

    subject = pelix.security.core.authenticate(UsernamePassword("thomas", "..."))
    # Subject(name='thomas', groups=['dev-leads'], roles=['admin'], ...)

    with run_as(subject):
        submit_job("nightly")

Secrets
=======

.. versionadded:: 3.3.0

A :class:`Secret` wraps a confidential value (a ``str`` or ``bytes`` password or token,
an ``int`` PIN, a dictionary of credentials...) so that it can travel through properties, configurations and logs
without being written in clear text by mistake:

==================================== ===============================================
Operation                            Behaviour
==================================== ===============================================
``repr()``, ``str()``, f-strings     ``Secret(***)`` or ``***``: the shell, the logs, the
                                     reports and the tracebacks show the mask
``reveal()``                         returns the value and raises the
                                     ``pelix.security.secret.reveal`` audit event
``==``                               compares two secrets (in constant time for
                                     ``str`` and ``bytes``), never a secret and a
                                     plain value
``equals(plain)``                    compares with a plain value, in constant time
                                     for text, and raises the audit event
``hash()``                           a keyed digest (process-random key): equal
                                     secrets hash alike, but not like their value
``bool()``, ``len()``                allowed: whether it is set is not confidential
``pickle``, ``json``                 refused (``TypeError``)
``copy``, ``deepcopy``               return the same object
==================================== ===============================================

The ``owner`` of a secret (a component instance, a factory or a configuration PID)
is not confidential: it tells who the secret was created for. :func:`to_secret`
wraps a plain value and keeps an existing secret, with its owner, as is.

Where secrets come from
-----------------------

* The properties declared with ``@HiddenProperty`` (see :doc:`ipopo_decorators`)
  are always ``Secret`` objects owned by the component instance: the declared
  default, the values given at instantiation, the confidential ``.name`` updates and
  the values the component sets itself. The component calls ``reveal()`` where it
  needs the value::

      @ComponentFactory("mqtt-client-factory")
      @HiddenProperty("_password", "mqtt.password", None)
      class Client:
          _password: Secret[str] | None

          @Validate
          def _validate(self, context):
              client.username_pw_set("user", self._password.reveal() if self._password else None)

* Configuration Admin keeps the text values of the keys matching the
  ``pelix.security.secret_keys`` framework property (comma-separated,
  case-insensitive ``fnmatch`` patterns, :data:`DEFAULT_SECRET_KEYS` by default,
  nothing if empty) as ``Secret`` objects owned by the
  configuration PID. ``Configuration.get_properties()`` gives them to every caller,
  iPOPO components and plain managed services alike. The JSON persistence stores
  them as ``{"$secret": "..."}`` in its private files and reads them back as secrets,
  whatever the patterns.
* The MQTT components accept a ``str`` or a ``Secret`` password and keep it as a
  secret until the connection.
* ``ShellSession.prompt_secret()`` reads a password typed in a shell command as a
  ``Secret[str]`` (see :doc:`shell`).

The credentials handled by a protocol rather than by a component property are not
secrets: the ``UsernamePassword`` of an authentication, the XMPP and etcd client
credentials and the remote services authentication keep plain ``str`` or
``bytearray`` values, as their libraries expect them.

The generic tools never reveal a secret: the shell commands, the log service and the
reports show the mask, the endpoints of Remote Services and Remote Service Admin leave
out the properties holding a secret, and the JSON-RPC, Jabsorb and XML-RPC transports
refuse to serialize one (``Secret._serialize()`` raises a ``TypeError`` for jsonrpclib).

LDAP filters
------------

In-process, a service property holding a secret is matched by the LDAP filters as its
value would be: ``(t=hunter2)``, ``(t=hun*)``, ``(t~=HUNTER2)`` and ``(t>=hunter1)`` all
match ``Secret("hunter2")``. A filter test raises no audit event: the filter reads the
value through an internal accessor of :mod:`pelix.security`, so that the service
registry doesn't flood the audit log.

A filter written by a remote caller would then be an unaudited oracle: ``(t=a*)``,
``(t=b*)``... guesses the value one character at a time. Such a filter **must** be
parsed with ``get_ldap_filter(text, untrusted=True)``: its criteria only test the
presence of a secret (``(t=*)`` matches, every other operator never matches, so
``(!(t=hunter2))`` always matches). The parsed object keeps that mode wherever it goes:
give it, not the string, to the service registry (``get_all_service_references()``,
``get_service_references()``), to ``ConfigurationAdmin.list_configurations()`` or to
``Configuration.matches()``, alone or combined with ``combine_filters()``.

The entry points which must parse their filters this way are those whose filter text
comes from the network: the ``filter`` parameter of the Web Console
(``GET services?filter=``, ``GET configadmin/configurations?filter=``), and any servlet,
remote service or shell command which takes a filter from its caller. The bundles of
Pelix take no such filter today.

Auditing the reveals
--------------------

Every call to ``reveal()`` raises the ``pelix.security.secret.reveal`` audit event
(:pep:`578`) with the owner of the secret and the name of the calling module. An
audit hook can't be removed once added, which suits a compliance log::

    import logging
    import sys

    from pelix.security import AUDIT_SECRET_REVEAL

    _audit = logging.getLogger("audit.secrets")

    def log_reveal(event, args):
        if event == AUDIT_SECRET_REVEAL:
            owner, module = args
            _audit.info("Secret of %s revealed by %s", owner, module)

    sys.addaudithook(log_reveal)

``grep -rn "reveal()\|equals("`` lists every disclosure point of the code for a
review: ``equals()`` tells whether a guess is right, so it is audited like ``reveal()``.
Comparing two secrets with ``==`` raises no event: both values are already held.

The audit sink bundle
---------------------

Installing ``pelix.security.audit`` instantiates a component (factory
``pelix.security.audit.factory``) writing to the ``pelix.security.audit`` logger:

* the EventAdmin events of the ``pelix/security/*`` topics (the component property
  ``event.topics`` changes them): ``AUTH_SUCCESS`` at the ``INFO`` level,
  ``AUTH_FAILURE`` and ``ACCESS_DENIED`` at the ``WARNING`` level, with their
  properties as ``key='value'`` pairs. A property holding a ``Secret``, or named after
  :data:`DEFAULT_SECRET_KEYS`, is left out. Those events need an EventAdmin service and
  ``pelix.security.core``;
* the reveal audit events, as
  ``secret revealed: owner='...' module='...' subject='...'``, with the name of the
  current subject. The audit hook stays installed (it can't be removed) but writes
  only while the component is valid.

That logger is a plain :mod:`logging` logger: send it to a persistent and, for NIS 2
traceability, preferably remote store, out of reach of the process, for example::

    import logging
    import logging.handlers

    audit = logging.getLogger("pelix.security.audit")
    audit.setLevel(logging.INFO)
    # Keep the trail out of the application logs
    audit.propagate = False
    audit.addHandler(logging.handlers.SysLogHandler(address="/dev/log"))
    # ... or a local file, rotated by logrotate
    audit.addHandler(logging.handlers.WatchedFileHandler("/var/log/pelix/audit.log"))

Expect some noise among the reveals, from the bundles doing their job: the JSON
persistence of Configuration Admin reveals each secret it writes to its files, the HTTP
services and the remote shell reveal their key password when they start, the MQTT
components reveal their password at each connection (reconnections included), and each
``equals()`` call is logged as a reveal. A reveal from another module, or for an
unexpected owner, is what stands out.

Limits
------

* **No enforcement.** In-process Python code reaches the value anyway (the slots of
  the object, ``gc``, ``ctypes``), and local bundles are trusted, as stated at the top
  of this page. The type makes the disclosures explicit and observable, it does not
  prevent them.
* **No memory wipe.** A ``str`` is immutable and can't be erased; the copies made by
  the libraries which receive the revealed value remain too.
* The key patterns of Configuration Admin are a heuristic: a false positive is a value
  the component has to reveal, a false negative is a value kept in clear text. Only
  ``str`` and ``bytes`` values are wrapped.
* **No encryption on disk.** ``{"$secret": "..."}`` in a configuration file is a
  marker which keeps the value a secret across restarts, not an encryption: the value
  is in clear text in the file. What protects it is the mode of the files (``0600``)
  and of their folder (``0700``), and who can read the disk and its backups.
* **The hash is not a digest to keep.** ``hash()`` uses a key drawn at each start of
  the process: it can't be stored nor compared with another process. For a ``str`` or
  ``bytes`` value it comes from an HMAC-SHA256; for any other value, it is the hash of
  the value mixed with that key, which only keeps it from being the hash of the plain
  value, it is not a cryptographic digest.
* **Login names are logged.** The authentication failures carry the user name as typed,
  in their events and in the audit trail: a password typed in the login field by
  mistake ends up there. Treat the audit trail as confidential, like the logs.

API
===

Beans
-----

.. autoclass:: Subject
   :members:

.. autoclass:: Credentials
   :members:

.. autoclass:: UsernamePassword
   :members:

.. autoclass:: ClientCertificate
   :members:

.. autoclass:: Permission
   :members:

.. autoclass:: Decision
   :members:

Secrets
-------

.. autoclass:: Secret
   :members: owner, reveal

.. autofunction:: to_secret

.. autodata:: AUDIT_SECRET_REVEAL

.. autodata:: PROP_SECRET_KEYS

.. autodata:: DEFAULT_SECRET_KEYS

Services
--------

.. autoclass:: Authenticator
   :members:

.. autoclass:: MembershipProvider
   :members:

.. autoclass:: Authorizer
   :members:

.. autoclass:: Authorization
   :members:

.. autofunction:: use_authorization

Exceptions
----------

.. autoclass:: SecurityError
.. autoclass:: AuthenticationFailed
.. autoclass:: AuthenticationRequired
.. autoclass:: AccessDenied

The pipeline
------------

.. autofunction:: pelix.security.core.authenticate

.. autofunction:: pelix.security.core.post_event

.. autoclass:: pelix.security.core.Throttle
   :members: is_locked, record_failure, record_success

The policy file
---------------

.. autofunction:: pelix.security.policy.normalize_fingerprint
