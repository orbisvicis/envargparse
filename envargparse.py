#!/usr/bin/env python3

import argparse
import os

import shlex


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
    # env_i:    Basic container type to identify unfilled arguments.
    env_k = "env_var"
    env_f = "env_var_parse"
    env_i = type("env_i", (object,), {})

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

        # Add the identifier to all valid environment variable actions for
        # later access by i.e. the help formatter.
        if env_k[1]:
            if env_v[1] and action.required:
                action.required = False
            i = self.env_i()
            i.a = action
            i.k = env_k[2]
            i.f = env_f[2]
            i.v = env_v[2]
            i.p = env_v[1]
            setattr(action, env_k[0], i)

        return action

    # Overriding "_parse_known_args" is better than "parse_known_args":
    #   * The namespace will already have been created.
    #   * This method runs in an exception handler.
    def _parse_known_args(self, arg_strings, namespace):
        """precedence: cmd args > env var > preexisting namespace > defaults"""

        for action in self._actions:
            if action.dest is argparse.SUPPRESS:
                continue
            try:
                i = getattr(action, self.env_k)
            except AttributeError:
                continue
            if not i.p:
                continue
            setattr(namespace, action.dest, i)

        namespace, arg_extras = super()._parse_known_args(arg_strings, namespace)

        for k,v in vars(namespace).copy().items():
            # Setting "env_i" on the action is more effective than using an
            # empty unique object() and mapping namespace attributes back to
            # actions.
            if isinstance(v, self.env_i):
                fv = v.f(v.a, v.k, v.v, arg_extras)
                delattr(namespace, k)
                if fv is not argparse.SUPPRESS:
                    # "_parse_known_args::take_action" checks for action
                    # conflicts. For simplicity we don't.
                    v.a(self, namespace, fv, v.k)

        return (namespace, arg_extras)

    def env_var_parse(self, a, k, v, e):
        # Use shlex, yaml, whatever.
        v = shlex.split(v)

        # From "_parse_known_args::consume_optional".
        n = self._match_argument(a, "A"*len(v))

        # From the main loop of "_parse_known_args". Treat additional
        # environment variable arguments just like additional command-line
        # arguments (which will eventually raise an exception).
        e.extend(v[n:])

        return self._get_values(a, v[:n])


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
class DefEnvArgHelpFormatter\
        ( EnvArgHelpFormatter
        , argparse.ArgumentDefaultsHelpFormatter
        ):
    pass


if __name__ == "__main__":
    # An example program:
    parser = EnvArgParser\
            ( prog="Test Program"
            , formatter_class=DefEnvArgHelpFormatter
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
