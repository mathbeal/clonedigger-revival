# How Clone Digger works

Clone Digger does not compare lines, nor tokens: it compares the shape of syntax trees,
and measures what is left over with **anti-unification**. This page walks through the
algorithm Peter Bulychev and Marius Minea described in *Duplicate Code Detection Using
Anti-Unification* (SYRCoSE 2008), as this port implements it: one tiny example for
anti-unification itself, then one small file taken from a bucket to a clone.

Every example below is run by `just test`: each `>>>` block is a doctest. The six
anti-unification cases are the ones recorded from the unmodified 1.1.0 release under
Python 2.7, in `tests/golden/anti_unification.json`.

## Anti-unification

### Unification, the other way round

**Unification** starts from two patterns with holes and looks for the values of the
holes that make the two patterns equal. That is what Prolog does: it goes from the
general to the particular.

**Anti-unification** goes the other way. It starts from two concrete expressions and
looks for the most specific pattern that both are instances of. Plotkin called it the
*least general generalization*; he and Reynolds described it independently, in the same
volume, in 1970.

### A tiny example

Take two assignments: a total and a rebate, each a price times a rate.

```
total = prix * 1.2
remise = prix * 0.9
```

Anti-unification is defined on labelled trees, whatever language they come from, so the
two trees are written here by hand, labels and leaves alike, as the recorded case of the
original writes them:

```pycon
>>> from clonedigger import Node, Variable, anti_unify, substitute
>>> def node(label, *children):
...     """A node with its children, as the recorded cases write them."""
...     return Node(label, children)
>>> first = node("Assign", node("total"), node("Mult", node("prix"), node("1.2")))
>>> second = node("Assign", node("remise"), node("Mult", node("prix"), node("0.9")))
>>> first
Assign(total, Mult(prix, 1.2))

```

Both have the shape "assign a name the product of a name and a constant". They differ in
two places: the name on the left, and the constant.

```
      tree 1                   tree 2                anti-unifier
      Assign                   Assign                   Assign
     /      \                 /      \                 /      \
 total      Mult         remise      Mult           X1        Mult
           /    \                   /    \                   /    \
       prix      1.2            prix      0.9            prix      X2
```

A **variable** marks a place where the two trees differ, and each side records what its
variable stands for. A variable is a hole of its own, distinct from every other, and it
is numbered as it is made over the life of the program; this page renumbers the holes of
a pattern from one so that the examples read the same every run.

```pycon
>>> def numbered(pattern):
...     """Write a pattern with its variables numbered from one, for this page."""
...     holes = [leaf for leaf in dict.fromkeys(pattern.leaves()) if isinstance(leaf, Variable)]
...     return substitute(pattern, {hole: Node(f"X{n}") for n, hole in enumerate(holes, start=1)})
>>> result = anti_unify(first, second)
>>> numbered(result.pattern)
Assign(X1, Mult(prix, X2))
>>> [repr(subtree) for subtree in result.left.values()]
['total', '1.2']
>>> [repr(subtree) for subtree in result.right.values()]
['remise', '0.9']

```

Filling the holes back in gives each tree again, which is what the pattern and the two
substitutions promise:

```pycon
>>> substitute(result.pattern, result.left) == first
True
>>> substitute(result.pattern, result.right) == second
True

```

### The three rules

Both trees are walked together, from the root:

1. the two nodes are **equal**, subtrees included: the node is kept as it is;
2. they have the **same label and the same number of children**: the label is kept, and
   each pair of children is anti-unified in turn;
3. **anything else**: a variable goes there, and each side records the subtree it
   stands for.

That is the `unify` function of `anti_unification.py` in Clone Digger 1.1.0, sixteen
lines in the release kept under `legacy/`, whose own comment admits that "everywhere is
written Unifier instead of AntiUnifier, for simplicity".

### The same difference, the same variable

When the same difference comes back, the same variable must be used. Comparing `a + a`
with `b + b`, the right pattern is `X1 + X1`, not `X1 + X2`: the first says "twice the
same thing", the second "two things", and the first is the more specific of the two.

```pycon
>>> numbered(anti_unify(node("Add", node("a"), node("a")),
...                     node("Add", node("b"), node("b"))).pattern)
Add(X1, X1)

```

The original looks, before making a variable, for one that already stands for exactly
that pair of subtrees, and reuses it; its `ignore_parametrization` flag turns the sharing
off. Here the pairs already seen are kept in a table, which does the same in one pass,
and `share_variables=False` turns it off:

```pycon
>>> numbered(anti_unify(node("Add", node("a"), node("a")),
...                     node("Add", node("b"), node("b")),
...                     share_variables=False).pattern)
Add(X1, X2)

```

### Measuring the difference

Deciding whether two pieces of code are clones needs a number. Each substitution weighs
the **distinct leaves** of the subtrees it puts in the holes, a name or a constant
counting 1, less 0.5 for each hole (`VARIABLE_COST`, `free_variable_cost` in the
original). The **distance** is the two substitutions added together, so two equal trees
are at distance 0.

```pycon
>>> from clonedigger import VARIABLE_COST
>>> VARIABLE_COST
0.5
>>> result.left_size, result.right_size, result.distance
(1.0, 1.0, 2.0)

```

These are the six cases recorded from the original:

| Tree 1 | Tree 2 | Pattern | Variables | Distance |
|---|---|---|--:|--:|
| `f(x)` | `f(x)` | `f(x)` | 0 | 0 |
| `a + a` | `b + b` | `X1 + X1` | 1 | 1 |
| `a + a` | `b + c` | `X1 + X2` | 2 | 2 |
| `total = prix * 1.2` | `remise = prix * 0.9` | `X1 = prix * X2` | 2 | 2 |
| `return a * b` | `return a + b` | `return X1` | 1 | 3 |
| `f(x)` | `f(x, y)` | `X1` | 1 | 4 |

```pycon
>>> cases = [
...     (node("Call", node("f"), node("x")), node("Call", node("f"), node("x"))),
...     (node("Add", node("a"), node("a")), node("Add", node("b"), node("b"))),
...     (node("Add", node("a"), node("a")), node("Add", node("b"), node("c"))),
...     (first, second),
...     (node("Return", node("Mult", node("a"), node("b"))),
...      node("Return", node("Add", node("a"), node("b")))),
...     (node("Call", node("f"), node("x")),
...      node("Call", node("f"), node("x"), node("y"))),
... ]
>>> [numbered(anti_unify(one, other).pattern) for one, other in cases]
[Call(f, x), Add(X1, X1), Add(X1, X2), Assign(X1, Mult(prix, X2)), Return(X1), X1]
>>> [anti_unify(one, other).distance for one, other in cases]
[0, 1.0, 2.0, 2.0, 3.0, 4.0]

```

Two things to read in that table. A **difference that repeats costs less** than two
separate ones: `a + a` against `b + b` is at 1, against `b + c` at 2. And
**anti-unification is purely syntactic**: `a * b` and `a + b` do not share their root in
the trees of the original, so the whole subtree becomes a variable although only the
operator changed, and a different number of children does the same to `f(x)` against
`f(x, y)`. This is the price of the third rule, and the reason a clone is looked for over
a run of statements rather than inside one.

## From a file to its clones

`detection.py` chains the steps below. They exist to avoid comparing every pair of
statements, which would grow with the square of the size of the code base. The example is
two functions that compute a total the same way, with other names and another rate; a
line-based tool sees nothing in common.

```pycon
>>> prices = '''def total_with_tax(items):
...     total = 0
...     for item in items:
...         price = item.price * item.quantity
...         if item.discount:
...             price = price - item.discount
...         total = total + price
...     total = total * 1.2
...     return round(total, 2)
...
...
... def total_with_rebate(lines):
...     amount = 0
...     for line in lines:
...         cost = line.price * line.quantity
...         if line.discount:
...             cost = cost - line.discount
...         amount = amount + cost
...     amount = amount * 0.9
...     return round(amount, 2)
... '''

```

### 1. Split into runs of statements

Each file is parsed with `ast` and cut into **sequences**: the runs of statements that
sit side by side in a body, a branch or a loop. Imports and docstrings are left out. Here
there are seven, one per body: two function bodies of four statements, two loop bodies of
three, two `if` bodies of one, and the module itself, whose two statements are the
function definitions.

```pycon
>>> from pathlib import Path
>>> from clonedigger.python_frontend import read_source
>>> source = read_source(Path("prices.py"), prices)
>>> [len(sequence) for sequence in source.sequences]
[1, 3, 4, 1, 3, 4, 2]

```

A sequence that spans fewer lines than `--size-threshold` (5 by default) cannot hold a
clone, and is dropped:

```pycon
>>> from clonedigger.detection import covered_lines
>>> sequences = [s for s in source.sequences if len(covered_lines(s)) >= 5]
>>> [len(sequence) for sequence in sequences]
[4, 4, 2]

```

A statement's tree keeps the labels of `ast`, with a name or a constant ending in a leaf
that holds its text, so that two trees differ exactly where a name or a value differs:

```pycon
>>> total, amount = sequences[0][0], sequences[1][0]
>>> total.tree
Assign(AssName('total'), Constant(0))
>>> amount.tree
Assign(AssName('amount'), Constant(0))

```

### 2. Hash the top of each statement

Each statement gets a hash of the **top of its tree** only, as deep as
`--hashing-depth` (1 by default). Leaves count for nothing, so two statements that differ
only in their names and their constants fall in the same bucket, and only statements of
the same bucket are ever compared.

```pycon
>>> from clonedigger.detection import dcup_hash
>>> dcup_hash(total.tree, 1) == dcup_hash(amount.tree, 1)
True
>>> dcup_hash(Node("price"), 1)
0

```

A statement of another kind lands elsewhere:

```pycon
>>> loop = sequences[0][1]
>>> loop.tree.label
'For'
>>> dcup_hash(total.tree, 1) == dcup_hash(loop.tree, 1)
False

```

The ten statements of the example fall in five buckets of two, each holding a statement
of each function:

```pycon
>>> from clonedigger.detection import buckets_by_shape
>>> buckets = buckets_by_shape(sequences, 1)
>>> sorted(len(statements) for statements in buckets.values())
[2, 2, 2, 2, 2]

```

### 3. Gather each bucket into clusters

Inside a bucket, statements are gathered into **clusters**, each keeping the
anti-unifier of its members as its pattern. A statement joins the cluster it costs least
to widen, as long as that cost stays at or under `--clustering-threshold` (10 by
default); otherwise it starts a cluster of its own. The cost counts the holes the pattern
would gain, once for each member it already holds, plus what the newcomer brings.

```pycon
>>> from clonedigger.detection import build_clusters
>>> bucket = buckets[dcup_hash(total.tree, 1)]
>>> clusters = build_clusters(bucket, 10)
>>> len(clusters)
1
>>> numbered(clusters[0].pattern)
Assign(AssName(X1), Constant(0))

```

### 4. Mark every statement

Each statement is then marked with the cluster whose pattern it is closest to, so that a
sequence of statements reads as a **string of marks**: a word whose letters are patterns
of statements. The two function bodies spell the same word, which is the whole point.

```pycon
>>> from clonedigger.detection import mark_statements
>>> for statements in buckets.values():
...     mark_statements(statements, build_clusters(statements, 10))
>>> first_body, second_body = (s for s in sequences if len(s) == 4)
>>> [s.mark for s in first_body] == [s.mark for s in second_body]
True

```

A run is cut out at this point once more than `MAX_EQUAL_MARKS` statements follow its
first one with the same mark: long lists of similar assignments match each other
everywhere and say nothing. `--force` keeps them.

```pycon
>>> from clonedigger.detection import MAX_EQUAL_MARKS
>>> MAX_EQUAL_MARKS
10

```

### 5. Find the runs that repeat, with a suffix tree

Every string of marks goes into a **suffix tree**, which hands back the longest runs
that occur in two places and cannot be extended to the left. Each pair is a candidate
clone. Here there are two: the two bodies of four statements, and the two function
definitions of the module body.

```pycon
>>> from clonedigger import SuffixTree
>>> suffixes = SuffixTree(lambda statement: statement.mark)
>>> for sequence in sequences:
...     suffixes.add(sequence)
>>> pairs = suffixes.iter_best_max_substrings(
...     5, lambda mark: mark.max_covered_lines, lambda run: len(covered_lines(run))
... )
>>> [(len(one), len(other)) for one, other in pairs]
[(4, 4), (1, 1)]

```

### 6. Refine each candidate

A candidate has the right shape, nothing more: its distance still has to be measured.
Each pair is shrunk to its longest window whose distance stays under
`--distance-threshold` (5 by default) and which still spans enough lines. Whatever is
left on each side of that window is searched again.

The four statements of the example are at distance 5, which a threshold of 5 does not
admit; their first two, the counter and the loop, are at 4.

```pycon
>>> from clonedigger.detection import sequence_tree
>>> anti_unify(sequence_tree(first_body), sequence_tree(second_body)).distance
5.0
>>> anti_unify(sequence_tree(first_body[:2]), sequence_tree(second_body[:2])).distance
4.0

```

### 7. Drop what lies inside something larger

Last, a clone whose two copies both sit inside the two copies of another clone says
nothing new, and is dropped. Here nothing is: the two function definitions are too far
apart to be a clone of their own, and the one clone left is the one the README shows.

```pycon
>>> from clonedigger.detection import find_clones
>>> clones = find_clones([source])
>>> len(clones)
1
>>> clone = clones[0]
>>> clone.distance
4.0
>>> min(covered_lines(clone.first)), max(covered_lines(clone.first))
(13, 18)
>>> min(covered_lines(clone.second)), max(covered_lines(clone.second))
(2, 7)

```

The thresholds of every step are the ones of Clone Digger 1.1.0, with its default
values. `Settings` carries them, where the original used module-level globals, so two
analyses can run side by side in one program; the command-line options that set them are
listed in the [README](../README.md).

```pycon
>>> from clonedigger.detection import Settings
>>> Settings()
Settings(size_threshold=5, distance_threshold=5, clustering_threshold=10, hashing_depth=1, force=False)

```

## References

- Peter Bulychev and Marius Minea. *Duplicate Code Detection Using Anti-Unification.*
  Proceedings of the Spring/Summer Young Researchers' Colloquium on Software Engineering
  (SYRCoSE), 2008. doi:10.15514/SYRCOSE-2008-2-22
- Peter Bulychev, Egor Kostylev and Vladimir Zakharov. *Anti-unification Algorithms and
  Their Applications in Program Analysis.* Perspectives of Systems Informatics, Lecture
  Notes in Computer Science, Springer, 2010, pp. 413-423.
  doi:10.1007/978-3-642-11486-1_35
- Gordon D. Plotkin. *A Note on Inductive Generalization.* Machine Intelligence 5,
  Edinburgh University Press, 1970.
- John C. Reynolds. *Transformational Systems and the Algebraic Structure of Atomic
  Formulas.* Machine Intelligence 5, Edinburgh University Press, 1970. The two founding
  texts of anti-unification, written independently the same year.
