"""Annotations from sanshain.yaml: named values Sanshain stores with the provided version or the system.

Their `{{NAME}}` placeholders are filled from the build: the CLI's
`--set NAME=value` first, else the environment variable `SANSHAIN_SET_NAME`
(the Conan integration has no flags and reads the environment only).
Needs Sanshain Service 2.13.0 or later; the service checks the limits.
"""

import os
import re

SET_ENV_PREFIX = "SANSHAIN_SET_"

# {{NAME}} with NAME of ASCII letters, digits and _ only; anything else
# between double braces ({{ A }}, {{a-b}}, {{}}) is literal text.
_PLACEHOLDER = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")


def parse_set(arg):
    """One `--set NAME=value`, split at the first `=` so the value may hold more."""
    name, sep, value = arg.partition("=")
    if not sep or not name:
        raise ValueError(f"expected NAME=value, got '{arg}'")
    return name, value


def fill_annotations(declared, sets=None, env=None, flag_hint=True):
    """The annotations as they are sent, and a warning per entry left out.

    A placeholder takes the `sets` value for its NAME first, else
    SANSHAIN_SET_NAME (exact case), and counts as filled only with a
    non-empty value; an empty `--set` does not fall through to the
    environment. An entry with an unfilled placeholder is left out, with a
    warning naming it and its first unfilled placeholder; the others are kept
    in order. `flag_hint` names `--set` in the warning (the CLI); without it
    only the variable is named (the Conan integration).
    """
    sets = sets or {}
    env = os.environ if env is None else env
    annotations = []
    warnings = []
    for entry in declared or []:
        missing = []

        def fill(match):
            name = match.group(1)
            found = sets[name] if name in sets else env.get(SET_ENV_PREFIX + name, "")
            if not found:
                missing.append(name)
            return found

        value = _PLACEHOLDER.sub(fill, entry["value"])
        if missing:
            name = missing[0]
            source = f"--set {name}=… or {SET_ENV_PREFIX}{name}" if flag_hint else f"{SET_ENV_PREFIX}{name}"
            warnings.append(f"annotation '{entry['name']}' left out: {{{{{name}}}}} is not set ({source})")
            continue
        # Exactly the three fields: an extra key in sanshain.yaml is only reported as unknown.
        annotations.append({"scope": entry["scope"], "name": entry["name"], "value": value})
    return annotations, warnings
