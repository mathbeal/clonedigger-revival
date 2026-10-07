# Clone Digger, revived for Python 3

**Clone Digger is the work of Peter Bulychev.** It finds duplicated code by comparing
the shape of syntax trees and measuring their differences with *anti-unification*, an
algorithm he designed with Marius Minea. It was written in 2008 during the Google
Summer of Code and last released, as version 1.1.0, in February 2010:
<http://clonedigger.sourceforge.net>.

That release runs on Python 2 only: it is built on the `compiler` module, which
Python 3.0 removed. This repository brings the same tool to current Python. The
goal is an update, not a new tool: same algorithm, same idea, same licence, kept
faithful to the original and credited to its authors.

> **Status: work in progress.** Nothing here is released yet. Until the original
> author has been asked, this project does not use the `clonedigger` name on PyPI,
> which remains his.

## What changes, and what does not

- **Kept**: the anti-unification algorithm, the clustering of statements, the suffix
  tree search for similar sequences, the thresholds and their meaning.
- **Changed**: the Python front end moves from `compiler` to the standard `ast`
  module; the code moves to Python 3.12 and later, typed and tested.
- **Left out for now**: the Java, JavaScript and Lua front ends generated with ANTLR,
  the bundled copy of `logilab-astng` and `logilab-common`, and the Eclipse plugin.
  They remain under `legacy/`, unmodified, and in the first commit.

Every change to the original is in the git history. The first commit is the 1.1.0
release, unmodified, recorded under Peter Bulychev's name; see [NOTICE.md](NOTICE.md).

## How it works

1. Each file is parsed and split into sequences of statements.
2. Statements are grouped into clusters of similar shape; each cluster keeps the
   anti-unifier of its members, the most specific pattern they all match.
3. Each statement is labelled with its cluster, so a file becomes a string of labels.
4. A suffix tree finds the longest runs of labels that appear in two places.
5. Each candidate pair is checked by anti-unification: it is reported as a clone when
   the two sides differ by less than a threshold.

Because it compares trees, not lines, it finds copies where names, constants or whole
sub-expressions were changed.

## Citing

If you use or study this tool, please cite the original work
([CITATION.cff](CITATION.cff)):

- Peter Bulychev and Marius Minea. *Duplicate Code Detection Using
  Anti-Unification.* Proceedings of the Spring/Summer Young Researchers' Colloquium
  on Software Engineering (SYRCoSE), 2008. doi:10.15514/SYRCOSE-2008-2-22
- Peter Bulychev, Egor Kostylev and Vladimir Zakharov. *Anti-unification Algorithms
  and Their Applications in Program Analysis.* Perspectives of Systems Informatics,
  Lecture Notes in Computer Science, Springer, 2010, pp. 413-423. doi:10.1007/978-3-642-11486-1_35

## Licence

GNU General Public License, version 3 or (at your option) any later version, as the
original: see [LICENSE](LICENSE). Files taken from Clone Digger keep
their original copyright notice; files that are modified say so, with the date.
