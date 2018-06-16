How to contribute
#################

All contributions to iPOPO are always welcome.

Issues & Feedback
=================

Issues must be described on the
`GitHub repository <https://github.com/tcalmant/ipopo/issues>`_.

Feedback is always greatly appreciated and should be given on the
`ipopo-users <https://groups.google.com/forum/#!forum/ipopo-users>`_
mailing list.

New features can be requested either as an *Enhancement* issue or discussed
on the users mailing list.


Code contribution
=================

In order io contribute code to iPOPO, you must fork the project then use
`GitHub Pull Requests <https://github.com/tcalmant/ipopo/pulls>`_.
Your code will be reviewed, tested and inserted into the master branch.

Your code style must follow some rules, described in the following section.

If you don't write documentation or tests, I'll write some of them; but
contributing both of them will increase the changes of your pull request to be
accepted.

Note that your contributions must be released under the project's license,
which is the `Apache Software License 2.0 <http://www.apache.org/licenses/LICENSE-2.0>`_.


Code Style
==========

Overall, try to respect `PEP-8 <https://www.python.org/dev/peps/pep-0008/>`_.

If you use PyCharm or VS Code, most of the rules described here are already
checked.

General
-------

* Your code must be compatible with Python 2.7 and 3.3+.
* Use ``logging`` instead of printing out debug traces.
* Use list, set and dictionary comprehension when possible.
* Remove unused imports.
* Imports must be after module documentation and before anything else.
* All modules must have a ``__version_info__`` tuple and a matching
  ``__version__`` string.

Formatting
----------

* Avoid inline comments; use 2 spaces when using them (mainly for type hinting)
* Break long lines after **80** characters. Exception for URLs and type hinting
  as they don't support line breaks
* Delete trailing whitespace.
* Don't include spaces after ``(``, ``[``, ``{`` or before ``}``, ``]``, ``)``.
* Don't misspell in method names.
* Don't vertically align tokens on consecutive lines.
* Use 4 spaces indentation (no tabs).
* Use an empty line between methods.
* Use 2 empty lines before class definitions.
* Use spaces around operators.
* Use spaces after commas and colons.
* Use Unix-style line endings (``\n``).
* Use 3 double-quotes (``"""``) for documentation


Naming
------

* Use ``CamelCase`` for class names.
* Use ``SNAKE_UPPERCASE`` for constants.
* Use ``snake_case`` for method names.
* ``CamelCase`` is allowed for decorator methods.
* First argument of:

  * instance methods must be ``self``
  * class methods must be ``cls``


Organization
------------

Documentation about a new feature should be added to a new file in
``docs/refcards``.

New features implementations can be added to either an existing or a new
``pelix`` subpackage.
You should not add new modules to the root ``pelix`` package.

Tests should be added to either an existing or a new sub-folder of ``tests``.
Unit tests are executed using ``nose`` and based on ``unittest2``.

You can also provide new samples in the ``samples`` folder. They must come as
a ``run_XXX.py`` entry-point script and an ``XXX`` package containing all
the sample bundles.
