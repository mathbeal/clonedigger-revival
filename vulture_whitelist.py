# Copyright 2026 Mathieu Béal
# SPDX-License-Identifier: GPL-3.0-or-later

"""Names vulture cannot see used, each with the reason it stays."""

from clonedigger import AntiUnification, Cluster, Node

# Public API: what a caller reads from an anti-unification, a cluster and a node.
_ = AntiUnification.variables
_ = AntiUnification.distance
_ = Cluster.max_covered_lines
_ = Node.covered_lines
