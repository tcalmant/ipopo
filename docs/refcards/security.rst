.. _refcard_security:
.. module:: pelix.security

Authentication and Authorization
################################

.. versionadded:: 3.3.0

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
How do I get credentials off this transport?   (transport-specific)           see the HTTP reference card
Are these credentials valid, and who is it?    :class:`Authenticator`         ``.htpasswd``
Which groups and roles does this subject have? :class:`MembershipProvider`    ``.htgroup``, policy file
May this subject do this?                      :class:`Authorizer`            policy file
============================================== ============================== ==========================

Plus exactly one facade, :class:`Authorization`, which is what application code
injects or reaches through :func:`use_authorization`.

Bundles
=======

============================= =============================================================
Bundle                        What it brings
============================= =============================================================
``pelix.security.core``       ``authenticate()``, the :class:`Authorization` facade
``pelix.security.htpasswd``   an :class:`Authenticator` and a :class:`MembershipProvider`
``pelix.security.policy``     roles from groups, permissions from roles, and the escape hatch
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

``pelix.security.core.authenticate(credentials)`` turns credentials into a subject:

1. every :class:`Authenticator` accepting this kind of credentials is consulted in
   ``service.ranking`` order;
2. every :class:`MembershipProvider` contributes groups, and the results are unioned;
3. the subject is rebuilt with those groups, and only then does every provider
   contribute roles;
4. the subject is returned, authenticated, with ``method`` left unset for the
   transport to stamp.

Step 3 is two passes rather than one, and that is load-bearing: it is what lets the
policy file grant a role from a group a *different* provider asserted. With a single
pass the policy would look at a subject whose groups are still empty and answer
nothing.

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

.. autoclass:: Permission
   :members:

.. autoclass:: Decision
   :members:

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
