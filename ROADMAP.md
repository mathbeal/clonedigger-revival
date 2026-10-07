# Roadmap

Each step ends with `just check` green and every mutant killed.

1. **Done: the core.** Trees, anti-unification, clusters, suffix tree, held to the
   answers of 1.1.0.
2. **Done: the Python front end**, on the standard `ast` module.
3. **Done: the detection pipeline**, in small functions with a `Settings` object. It
   finds the clone the original found on `tests/golden/inputs/`, at the same lines.
4. **Done in part: the command line**, with text and JSON reports. To come: SARIF for
   code scanning tools, then the HTML report of the original.
   **Done: mutation testing** of the whole package: all 743 mutants are caught, 741
   by a failing test and 2 by a time-out (they make refinement loop forever).
   997 mutants today, all caught.
5. **Measure.** Done for speed: the whole standard library of Python 3.14 (455,000
   lines, tests left out) takes 62 s instead of 222 s, with the same 9,579 clones
   (`just bench`). To come: compare with pylint `duplicate-code` and jscpd on real
   projects, and show the clones only anti-unification finds.
6. **Publish**, with the original author's agreement on the name: continuous
   integration, attested releases on PyPI, documentation.

The fixes of the 1.1.0 bugs found while porting are listed in the commits that make
them. The Java, JavaScript and Lua front ends of the original are out of scope until
the Python one is done.
