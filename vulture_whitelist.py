# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""Names vulture cannot see used, each with the reason it stays."""

from clonedigger import AntiUnification

# Public API: what a caller reads from an anti-unification.
_ = AntiUnification.variables
