# Copyright 2008 Peter Bulychev (Clone Digger 1.1.0)
# Copyright 2026 Mathieu Béal (port to Python 3, 2026)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Clone Digger, by Peter Bulychev: duplicate code detection by anti-unification.

This is a port of Clone Digger 1.1.0 (2010) to Python 3. The algorithm is described
in Peter Bulychev and Marius Minea, "Duplicate Code Detection Using
Anti-Unification", SYRCoSE 2008.
"""

from importlib.metadata import version

from clonedigger.anti_unification import AntiUnification, Cluster, anti_unify, substitute
from clonedigger.suffix_tree import SuffixTree
from clonedigger.tree import VARIABLE_COST, Node, Variable

__version__ = version("clonedigger-revival")

__all__ = [
    "VARIABLE_COST",
    "AntiUnification",
    "Cluster",
    "Node",
    "SuffixTree",
    "Variable",
    "__version__",
    "anti_unify",
    "substitute",
]
