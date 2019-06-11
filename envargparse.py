#!/usr/bin/env python3

import argparse
import os
import collections

import shlex

import decorator


EnvArgRecord = collections.namedtuple\
        ( "EnvArgRecord"
        , [ "a"
          , "k"
          , "f"
          , "v"
          , "p"
          ]
        )
# This record is attached to all actions presenting the environment-variable
# key, whether or not the environment-variable value is actually set.
EnvArgRecord.__doc__ = "Record of associated environment-variable values."
EnvArgRecord.a.__doc__ = "action"
EnvArgRecord.k.__doc__ = "key"
EnvArgRecord.f.__doc__ = "function"
EnvArgRecord.v.__doc__ = "value"
EnvArgRecord.p.__doc__ = "present"


# Notes:
#   * Based on https://github.com/python/cpython/blob/
#               15bde92e47e824369ee71e30b07f1624396f5cdc/
#               Lib/argparse.py
#   * Haven't looked into handling "required" for mutually exclusive groups
#   * Probably should make new attributes private even though it's ugly.
class EnvArgParser(argparse.ArgumentParser):
    # env_k:    The keyword to "add_argument" as well as the attribute stored
    #           on matching actions.
    # env_f:    The keyword to "add_argument". Defaults to "env_var_parse" if
    #           not provided.
    env_k = "env_var"
    env_f = "env_var_parse"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # The ArgumentParser class would have been more flexible having
        # _parse_known_args::seen_actions available at the class-level. It was
        # probably kept within the parsing function because it is only valid up
        # until and must be reset before a subsequent parse.
        #
        # Nonetheless, here we are. It is generally useful to know whether a
        # command-line argument has been provided.
        self.seen_actions = set()

        # There are four public parsing methods:
        #   * parse_args
        #   * parse_known_args
        #   * parse_intermixed_args
        #   * parse_known_intermixed_args
        #
        # The setup and teardown code for each of these methods is handled by
        # the setup_parse decorator:
        #   * clear seen_actions
        #   * fetch environment variables for missing actions
        #
        # The *intermixed* methods call parse_known_args twice but this should
        # not cause the decorator to run more than once. This attribute tracks
        # the parsing depth; only when it is zero will the setup/teardown code
        # execute.
        #
        # The property version of this attribute ensures it is never below
        # zero.
        self._parsing_depth = 0

    @property
    def parsing_depth(self):
        return self._parsing_depth

    @parsing_depth.setter
    def parsing_depth(self, value):
        self._parsing_depth = max(value, 0)

    def add_argument(self, *args, **kwargs):
        map_f = (lambda m,k,f=None,d=False:
                    (k, k in m, m.pop(k,f) if d else m.get(k,f)))

        env_k = map_f(kwargs, self.env_k, d=True, f="")
        env_f = map_f(kwargs, self.env_f, d=True, f=self.env_var_parse)

        if env_k[1] and not isinstance(env_k[2], str):
            raise ValueError(f"Parameter '{env_k[0]}' must be a string.")

        if env_f[1] and not env_k[1]:
            raise ValueError(f"Parameter '{env_f[0]}' requires '{env_k[0]}'.")

        if env_f[1] and not callable(env_f[2]):
            raise ValueError(f"Parameter '{env_f[0]}' must be callable.")

        action = super().add_argument(*args, **kwargs)

        if env_k[1] and not action.option_strings:
            raise ValueError(f"Positional parameters may not specify '{env_k[0]}'.")

        # We can get the environment now:
        #   * We need to know now if the keys exist anyway
        #   * os.environ is static
        env_v = map_f(os.environ, env_k[2], f="")

        # Examples:
        # env_k:
        #   ("env_var", True,  "FOO_KEY")
        # env_v:
        #   ("FOO_KEY", False, "")
        #   ("FOO_KEY", True,  "FOO_VALUE")
        #
        # env_k:
        #   ("env_var", False, "")
        # env_v:
        #   (""       , False, "")
        #   ("",        True,  "RIDICULOUS_VALUE")

        # Add the record to all valid environment variable actions for later
        # access by i.e. the help formatter.
        if env_k[1]:
            if env_v[1] and action.required:
                action.required = False
            i = EnvArgRecord\
                    ( a=action
                    , k = env_k[2]
                    , f = env_f[2]
                    , v = env_v[2]
                    , p = env_v[1]
                    )
            setattr(action, env_k[0], i)

        return action

    def _add_action(self, action):
        # Count how often each action is called, among other useful features.
        action = EnvArgAction(action)
        return super()._add_action(action)

    # The setup and teardown code for each parsing method. This is what runs
    # parse_args_post, fetching environment variables for missing actions. See
    # the comments at __init__::_parsing_depth for more information.
    #
    # precedence: cmd args > env var > preexisting namespace > defaults
    @decorator.decorator
    def setup_parse(f, self, *args, **kwargs):
        run_setup = not self.parsing_depth

        if run_setup:
            self.seen_actions.clear()

        self.parsing_depth += 1
        try:
            namespace, arg_extras = f(self, *args, **kwargs)
        finally:
            self.parsing_depth -= 1

        if run_setup:
            self.parse_args_post(namespace, arg_extras)

        return namespace, arg_extras

    parse_known_args = setup_parse\
            (argparse.ArgumentParser.parse_known_args)

    parse_known_intermixed_args = setup_parse\
            (argparse.ArgumentParser.parse_known_intermixed_args)

    @decorator.decorator
    def argument_error_and_exit(f, self, *args, **kwargs):
        try:
            return f(self, *args, **kwargs)
        except argparse.ArgumentError as e:
            self.error(str(e))

    # Because of the *intermixed* methods we can't piggyback off the exception
    # handler of _parse_known_args (see previous versions).
    @argument_error_and_exit
    def parse_args_post(self, namespace, arg_extras):
        for action in self._actions:
            if action.dest is argparse.SUPPRESS:
                continue
            # An action can be seen but not called if its value is SUPPRESS.
            # For example, "_get_values" will produce SUPPRESS when parsing an
            # option without any arguments if "nargs" is OPTIONAL ("?") and
            # "const" is SUPPRESS. When this happens we should process the
            # matching environment variable argument.
            #
            # There is no reason an action would be called but not seen, but if
            # this happens we should also process the matching environment
            # variable argument.
            if action.call_count > 0 and action in self.seen_actions:
                continue
            try:
                i = getattr(action, self.env_k)
            except AttributeError:
                continue
            if i.a is not action:
                continue
            if not i.p:
                continue
            # Actions provided via the command-line are marked as seen when
            # super()._parse_known_args calls self._get_values. Actions
            # provided via the environment may be marked as seen if the "env_f"
            # function calls self._get_values. This happens with the default
            # function, self.env_var_parse, but is not guaranteed. Therefore we
            # now mark the action as seen even though it may be redundant.
            self.seen_actions.add(action)
            # Parse the environment variable.
            v,e = i.f(self, i.a, i.k, i.v)
            # From the main loop of "_parse_known_args". Treat additional
            # environment variable arguments just like additional command-line
            # arguments (which will eventually raise an exception).
            arg_extras.extend(e)
            # Ignore suppressed values.
            if v is argparse.SUPPRESS:
                continue
            # "_parse_known_args::take_action" checks for action
            # conflicts. For simplicity we don't.
            i.a(self, namespace, v, i.k)

        return (namespace, arg_extras)

    # Environment variable parsers need not be methods. The parser (self) will
    # be passed in as the first argument anyway. Feel free to raise
    # ArgumentError here. Returns the 2-tuple (used_values, extra_values).
    @staticmethod
    def env_var_parse(p, a, k, v):
        # Use shlex, yaml, whatever.
        v = shlex.split(v)

        # From "_parse_known_args::consume_optional". Split the list of
        # arguments into those that will be consumed and extra arguments.
        n = p._match_argument(a, "A"*len(v))

        # Convert/check/etc the value.
        return (p._get_values(a, v[:n]), v[n:])

    # In cooperation with EnvArgAction the _get_value(s) methods allow
    # overloading their ArgumentParser counterparts on a per-action basis. By
    # default EnvArgAction calls the matching method from EnvArgParser's base
    # class, so out-of-the-box there is no behavioral change.

    def _get_values(self, action, arg_strings):
        # Here we update our own set of seen actions. Mainly for command-line
        # arguments, but may also be useful for environment-variable parsers.
        self.seen_actions.add(action)

        return action.get_values(arg_strings, self)

    def _get_value(self, action, arg_string):
        return action.get_value(arg_string, self)


class Container:
    """A container class. Except names within the "excludes" list, all
    attribute access is forward to the contained object.
    """
    excludes = []

    def exclude(excludes):
        def decorator(f):
            excludes.append(f.__name__)
            return f
        return decorator

    def __new__(cls, obj, *args, **kwargs):
        if isinstance(obj, cls):
            return obj
        else:
            return super().__new__(cls)

    def __init__(self, obj):
        super().__setattr__("object", obj)

    @exclude(excludes)
    def unwrap(self):
        return super().__getattribute__("object")

    def __getattribute__(self, name):
        excludes = type(self).excludes

        if name in excludes:
            return super().__getattribute__(name)
        else:
            return getattr(self.unwrap(), name)

    def __setattr__(self, name, value):
        excludes = type(self).excludes

        if name in excludes:
            return super().__setattr__(name, value)
        else:
            return setattr(self.unwrap(), name, value)

    def __delattr__(self, name):
        excludes = type(self).excludes

        if name in excludes:
            return super().__delattr__(name)
        else:
            return delattr(self.unwrap(), name)


# Since __call__ uses special method lookup, it isn't possible to replace the
# __call__ method of an Action instance. The following won't work, for example:
#
#   action.__call__ = f(action.__call__).__get__(action, type(action))
#
# Therefore we use a container class that forwards all attribute access to
# contained action, and implement our own __call__. Since __call__ uses special
# method lookup it bypasses __getattribute__ and doesn't need to be added to
# the exclusion list.
class EnvArgAction(Container):
    """Every Action instance within EnvArgParser is wrapped by this container
    class, which serves several purposes. It increments a counter each time it
    is called, which is useful for tracking whether an action has been seen and
    consumed. In cooperation with EnvArgParser it allows the default
    ArgumentParser implementation of _get_values/_get_value to be overloaded on
    a per-action basis:
        1. EnvArgParser::_get_value(s) calls Action::get_value(s)
        2. Action::get_value(s) calls super(EnvArgParser)::_get_value(s)

    So by default there is no change to the behavior of _get_value(s).
    """

    excludes = Container.excludes[:] + ["call_count"]

    def __init__(self, action):
        super().__init__(action)
        self.call_count = 0

    def __call__(self, *args, **kwargs):
        self.call_count += 1
        return self.unwrap()(*args, **kwargs)

    # The following cooperative methods are fully supported by EnvArgParser.
    # Though they don't change the default behavior they're a nice showcase for
    # what's possible and perhaps useful for user-defined child classes.

    @Container.exclude(excludes)
    def get_values(self, arg_strings, parser):
        return super(type(parser), parser)._get_values(self, arg_strings)

    @Container.exclude(excludes)
    def get_value(self, arg_strings, parser):
        return super(type(parser), parser)._get_value(self, arg_strings)


# Derived from "ArgumentDefaultsHelpFormatter".
class EnvArgHelpFormatter(argparse.HelpFormatter):
    """Help message formatter which adds environment variable keys to
    argument help.
    """

    env_k = EnvArgParser.env_k

    # This is supposed to return a %-style format string for "_expand_help".
    # Since %-style strings don't support attribute access we instead expand
    # "env_k" ourselves.
    def _get_help_string(self, a):
        h = super()._get_help_string(a)
        try:
            i = getattr(a, self.env_k)
        except AttributeError:
            return h
        s = f" ({self.env_k}: {i.k})"
        if s not in h:
            h += s
        return h


# An example mix-in.
class EnvArgDefaultsHelpFormatter\
        ( EnvArgHelpFormatter
        , argparse.ArgumentDefaultsHelpFormatter
        ):
    pass


if __name__ == "__main__":
    # An example program:
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

    # Example program output:
    #
    # $ BAR="1 2 3 '45  ' 6 7" ./envargparse.py 123
    # Namespace(bar=[1, 2, 3, 45, 6, 7], baz=123)
    #
    # $ ./envargparse.py -h
    # usage: Test Program [-h] --bar BAR [BAR ...] baz
    #
    # positional arguments:
    #   baz
    #
    # optional arguments:
    #   -h, --help           show this help message and exit
    #   --bar BAR [BAR ...]  Help message for bar. (default: 22) (env_var: BAR)
