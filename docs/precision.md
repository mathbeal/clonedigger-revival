# Precision: what counts as duplicated code, and the figure

Clone Digger reports pairs of code it holds to be copies of one another. Precision is the
share of those pairs that a reader agrees are duplicated code. It cannot be computed: it
has to be judged, pair by pair, and the judgement has to be written down before the pairs
are read, or it follows the answer it is meant to measure.

This page is that judgement: the criteria first, then how the sample was drawn, then the
figure and how to obtain it again.

## The question asked of each pair

> If one copy changed, would the other have to change with it?

A pair is **duplicated code** when the answer is yes: the two copies say the same thing
twice, so a reader keeping them both has to keep them in step. It is **not** duplicated
code when the answer is no: the two blocks happen to be built alike and a change to one
has no bearing on the other.

Nothing else is asked. Whether the duplication is worth removing, whether it was written
on purpose, whether a language gives any way to avoid it: none of that is part of the
question. A pair of twins written out deliberately is still duplicated code.

### Counts as duplicated code

1. The two copies do the same work and differ only in their names, their constants,
   their strings, the attributes they reach or the types they name.
2. The two copies are the same code with one part changed: an argument more, another call
   in the middle, a condition one has and the other has not.
3. The two copies are the same code written out for two sibling things: a synchronous
   method and its asynchronous twin, two HTTP verbs, two fields of one kind, a backend
   and the backend beside it.
4. The two copies belong to a family written on one pattern, each member differing in its
   values: locale tables, settings declared one after the other, generated code.

### Does not count as duplicated code

5. The two copies share the shape of their statements and nothing that carries meaning:
   the same control flow over unrelated work, no name, call or constant in common.
6. What the two copies have in common is only the frame around the work: a `try` with an
   `except` raising different errors, a `super().__init__()` followed by assignments of
   different fields, a `with` around different bodies, a `return` of a different
   expression.
7. One of the two copies is cut across what it does: the lines reported start or stop in
   the middle of a unit, so they do not stand for anything a reader could share or move.
8. The two copies are each other's neighbours in a list of declarations, held together by
   the punctuation of the language rather than by any work they both do.

A pair that two of these criteria pull in opposite directions is judged on the first one
that applies, 1 to 8 in order, and the reason recorded with the verdict says which.

## Pairs whose two copies overlap

In a run of similar statements, a window and the same window shifted by a statement or
two can both be reported, as 1.1.0 did. Whether such a pair should be reported at all is
an open question of the [roadmap](../ROADMAP.md), and it is not settled here: the pair is
judged on its content like any other, and counted apart as well. The table below gives
precision over the whole sample, over the overlapping pairs and over the sample without
them, so that the answer to that question cannot move the figure quoted without saying
so.

## The sample

Two of the pinned projects of `just compare` are read, one library and one framework:

- **httpx 0.28.1**, 8,828 lines, a library of a few thousand lines;
- **Django 6.1.2**, 165,376 lines, a framework with large families of near-identical
  files.

The detection runs with its defaults, the same as in the comparison table of the README:
copies of at least 5 lines, distance at most 5. From each project, **30 pairs** are drawn
at random out of every pair it reports, which makes a sample of **60**. The same number
from each, so that the project reporting the more pairs does not drown the other: the
figure is therefore the precision over these two samples side by side, not the precision
over the nine projects of the comparison, and it is not weighted by how many pairs each
project reports.

The draw is `random.Random(seed).sample` over the pairs put in the order of where they
lie, so it does not depend on the order the report happens to list them in. The seed is
**1**, the first one tried: a seed chosen after seeing the figure would be choosing the
figure. The pairs drawn are in
[benchmarks/sample.json](../benchmarks/sample.json), the verdict and its reason for each
one in [benchmarks/labels.jsonl](../benchmarks/labels.jsonl). Both are committed, so the
figure can be checked without drawing anything again, and a verdict that looks wrong can
be argued with, pair by pair.

## The figure

    just precision

Every share is rounded away from the tool's advantage: precision and the lower bound
down, the upper bound up. The exact count stands next to each one.

<!-- The table below is the output of `just precision`. -->

## Drawing it again

    just sample     # writes benchmarks/sample.json again: same pairs, same order
    just label --report benchmarks/sample.json --root ~/.cache/clonedigger-bench
    just precision

`just sample` needs the archives of the two projects, which it downloads once from PyPI
and checks against their SHA-256, as `just compare` does. `just label` shows the two
copies of each pair side by side and asks for the verdict, leaving out the pairs already
judged. `just precision` reads the two files and nothing else.
