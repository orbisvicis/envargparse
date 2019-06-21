===========
EnvArgParse
===========

Argparse with environment variables. This module is both a derived `argparse`
class supporting environment variables and a framework or set of proposed
enhancements for extending `argparse`.

The Example
===========

The following is taken from the `__main__` conditional at the end of this module::

    parser = EnvArgParser\
            ( prog="Test Program"
            , formatter_class=EnvArgDefaultsHelpFormatter
            )

    parser.add_argument\
            ( '--bar'
            , required=True
            , env_var="BAR"
            , type=int
            , nargs="+"
            , default=22
            , help="Help message for bar."
            )

    parser.add_argument\
            ( 'baz'
            , type=int
            )

    args = parser.parse_args()
    print(args)

Example output::

   $ BAR="1 2 3 '45  ' 6 7" ./envargparse.py 123
   Namespace(bar=[1, 2, 3, 45, 6, 7], baz=123)

::

   $ ./envargparse.py -h
   usage: Test Program [-h] --bar BAR [BAR ...] baz

   positional arguments:
     baz

   optional arguments:
     -h, --help           show this help message and exit
     --bar BAR [BAR ...]  Help message for bar. (default: 22) (env_var: BAR)


How it Works
============

This module tries to be very simple: it may look longer because it is well-commented. There is no code duplication. In fact version 0.1 (tagged) was even simpler: actions were tracked via the namespace argument of `parse_args()`, maintaining the precedence:

   cmd args > env var > preexisting namespace > defaults

Basically it stores within the namespace a unique instance for each action with an environment variable key, if that variable exists. After `argparse` finishes parsing it executes the action associated with each remaining unique instance. The idea is this: if the action was provided via the command-line, it'll have been overwritten from the namespace.

You can still use that version if you want, but it doesn't handle actions which fail to set the `dest` attribute on the namespace. To be fair, such actions are exceedingly unlikely. For a while I considered sandboxing an empty namespace for each action and copying only the `dest` attribute back to the main namespace, but that would be artificially limiting. Instead...

Version 0.2 (tagged) is built around tracking actions. Whether an action has been seen as a command-line argument, and how often it has been called. Believe it or not, there are edge cases in which an action can be seen but not called. See the comments for more information.

The `EnvArgParser` class maintains the set of seen actions while every action, environment variable key or not, is embedded within a tracking object. Originally a function-local variable within the parsing function, the set of seen actions is lifted into the instance namespace and reset before each new parsing pass. Luckily there is a 1:1 call correspondence between seeing an action and calling `_get_values`, which now updates the set of seen actions. Each tracking object increments a counter whenever called and otherwise behaves exactly like the contained action, forwarding (almost) all attribute access.

An environment variable record, `EnvArgRecord`, is attached to each valid environment variable action whether or not that environment variable actually exists - for help-formatting reasons. Such actions will only be executed if the environment variable is available and the action hasn't already been seen or been called.

As for actually parsing the environment variable, that hasn't changed much between 0.1 and 0.2. Reflecting that the parsing function can be overridden per action, the default `env_var_parse` is a static method; the first argument is always the parser. The default mimics the parsing of `argparse` (counting, converting and checking values) without code duplication by relying on internal `ArgumentParser` methods. It's actually quite simple - just two method calls. The arguments are split using `shlex` but your custom parser can use `yaml`, `json`, or whatever else you prefer. Whatever the case, the parsing function must return a tuple: the resulting value(s) and a list of extra values. As extra values usually raise an exception you might consider leaving this empty.

And that's basically it, aside the from the value-checking boilerplate. As of python 3.7 the newly introduced intermixed parsing methods perform two-pass parsing, forcing `EnvArgParser` to track the parsing "depth". The set of seen actions is only cleared before this two-pass process and the environment variables only parsed afterwards - both at the uppermost depth.

There is a help formatter which adds environment variable keys to the argument help, and an example mix-in class with `argparse.ArgumentDefaultsHelpFormatter` to add both environment variable keys and argument defaults. Custom help formatters can be created simply by inheriting from the appropriate base classes.

What comes next is just icing on top of the cake. While it isn't actually used by this module nor does it change the default behavior it's a nice showcase for what's possible and perhaps useful for user-defined derived classes.

The original `ArgumentParser` is relatively monolithic while `EnvArgParser` uses cooperative OOP between action and parser to allow per-action overrides of parser methods. Whereas the parser would normally call its own methods it now calls into the action. By default the action calls the matching method from the parser's base class, so out-of-the-box there is no behavioral change. As a proof-of-concept this is only implemented for `_get_values` and `get_value` but if useful can be extended to all methods via a custom `__getattribute__`. In the meantime feel free to add additional methods or override the default behavior by deriving from `EnvArgParser` and `EnvArgAction`.

The Proposal
============

Let's step a bit back. Why can't you just use argument defaults::

   import argparse
   import os

   parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
   parser.add_argument("--foo", default=os.environ.get("FOO","bar"), help="FOO!")
   parser.parse_args()

That creates an artificial dependency between the default and the environment. In other words, it's not what the user expects. Notice how the default doesn't stay constant::

   $ ./test.py -h
   usage: test.py [-h] [--foo FOO]

   optional arguments:
     -h, --help  show this help message and exit
     --foo FOO   FOO! (default: bar)

::

   $ FOO=456 ./test.py -h
   usage: test.py [-h] [--foo FOO]

   optional arguments:
     -h, --help  show this help message and exit
     --foo FOO   FOO! (default: 456)


Unfortunately `argparse` is too much of a black box to cleanly modify and therefore this module serves as a working roadmap for proposed improvements. The important points:

* Be more transparent about parsing.

  Maintain parsing state, such as the set of seen actions, within the instance namespace rather than as inaccessible method variables. Track parsing depth during multistage parsing. Have the base `Action` class track how often it has been called. Mark core parsing methods as a part of the public API.

* Make parsing more modular.

  Create re-usable entry-points (methods) for:

  * parsing individual optional arguments.
  * parsing individual positional arguments.
  * checking for conflicts based on argument values.
  * handling exceptions (as a decorator).

  Right now the code is too monolithic.

* Don't force each argument to use the same parsing chain.

  Allow actions to overload important parser methods such as `_get_values`, `_get_value` or `_match_argument`.

The more trivial points:

* Switch to new-style (`{}`) string formatting.

  Old-style (`%`) string formatting cannot access object attributes. The `_get_help_string` method is expected to return a format string which would be unable to access attributes of `EnvArgRecord`.

The Module
==========

The code is well-commented, so here is a brief list of the provided classes:

* `EnvArgRecord`
* `EnvArgParser`
* `EnvArgAction`
* `EnvArgHelpFormatter`
* `EnvArgDefaultsHelpFormatter`
* `Container`

Requirements
============

   * Python 3.7+
   * module: `decorator` (`@PyPI`__)

__ decoratorPyPI_

License
=======

   GPLv3+; see `LICENSE.txt`

Author
======

   Yclept Nemo <pscjtwjdjtAhnbjm/dpn>

Links
=====

   * `EnvArgParse@GitHub`__
   * `EnvArgParse@PyPI`__

__ envargparseGitHub_
__ envargparsePyPI_


.. _decoratorPyPI:      https://pypi.org/project/decorator/
.. _decoratorGitHub:    https://github.com/micheles/decorator

.. _envargparsePyPI:    https://pypi.org/project/envargparse/
.. _envargparseGitHub:  https://github.com/orbisvicis/envargparse
