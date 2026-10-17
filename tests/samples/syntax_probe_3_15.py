# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

# Input of tests/test_syntax.py, kept apart because Python 3.15 is the first release
# that parses it: a lazy import (PEP 810), unpacking in a comprehension (PEP 798) and
# a literal pattern with a unary plus. Written twice under other names, as the other
# probe is, so that each construct can be read and found as a clone. The only unary
# plus of the file is the one in a pattern. Not meant to run.

lazy import json
lazy from pathlib import Path


def flatten_a(rows):
    flat = [*row for row in rows]
    kinds = {*row for row in rows}
    merged = {**row for row in rows}
    stream = (*row for row in rows)
    return flat, kinds, merged, stream


def flatten_b(items):
    plain = [*item for item in items]
    sorts = {*item for item in items}
    joined = {**item for item in items}
    flow = (*item for item in items)
    return plain, sorts, joined, flow


def sign_a(value):
    match value:
        case +1:
            name = "up"
        case +2:
            name = "twice up"
    return name


def sign_b(number):
    match number:
        case +1:
            label = "up"
        case +2:
            label = "twice up"
    return label
