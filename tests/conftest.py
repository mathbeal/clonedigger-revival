# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""Hypothesis profiles: the default for every run, and `fuzz` for long searches."""

import os

from hypothesis import settings

settings.register_profile(
    "fuzz",
    max_examples=int(os.environ.get("CLONEDIGGER_FUZZ_EXAMPLES", "50000")),
    deadline=None,
)
