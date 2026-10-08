# Roadmap

Each step ends with `just check` green and every mutant killed.

1. **Done: the core.** Trees, anti-unification, clusters, suffix tree, held to the
   answers of 1.1.0.
2. **Done: the Python front end**, on the standard `ast` module.
3. **Done: the detection pipeline**, in small functions with a `Settings` object. It
   finds the clone the original found on `tests/golden/inputs/`, at the same lines.
4. **Done: the command line**, with text, JSON, SARIF and HTML reports.
   **Done: mutation testing** of the whole package: every mutant is caught, by a
   failing test or by a time-out (a mutant that makes refinement loop forever).
5. **Measure.** Done for speed: the whole standard library of Python 3.14 (455,000
   lines, tests left out) takes 50 s and 1.1 GB instead of 222 s and 2.6 GB, with the
   same 9,579 clones (`just bench`); a run of 800 similar statements, with `--force`,
   takes about 20 s instead of more than four minutes. Done for comparison: pylint
   `duplicate-code` and jscpd on seven pinned releases of well-known projects, time,
   memory, pairs and share of lines (`just compare`, README).
   To come: measure precision over every pair on a labelled sample; decide whether a
   pair whose two copies overlap (a run of similar statements and the same run shifted)
   should be reported, which 1.1.0 did.
6. **Done: continuous integration** (every gate, Python 3.12 to 3.14 on Linux, macOS and
   Windows, mutation weekly), REUSE licensing, the README.
7. **Publish**, with the original author's agreement on the name: attested releases
   on PyPI.

The fixes of the 1.1.0 bugs found while porting are listed in the commits that make
them. The Java, JavaScript and Lua front ends of the original are out of scope until
the Python one is done.
