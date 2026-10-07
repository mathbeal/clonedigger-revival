# Roadmap

Each step ends with `just check` green and every mutant killed.

1. **Done: the core.** Trees, anti-unification, clusters, suffix tree, held to the
   answers of 1.1.0.
2. **The Python front end.** Turn source code into trees with the standard `ast`
   module, and split it into sequences of statements, as `python_compiler.py` did with
   the Python 2 `compiler` module. Record from the original how it splits a few files.
3. **The detection pipeline.** Hashing, clustering, marking, the suffix tree search,
   refinement by distance, removal of dominated clones: `clone_detection_algorithm.py`,
   split into small functions, configuration passed as arguments instead of globals.
   The clone report of the original on `tests/golden/inputs/` is the reference.
4. **The command line and the reports.** Text, JSON, and SARIF for code scanning
   tools; the HTML report of the original comes last.
5. **Measure.** Compare with pylint `duplicate-code` and jscpd on real projects, and
   show the clones only anti-unification finds. Profile the quadratic parts.
6. **Publish**, with the original author's agreement on the name: continuous
   integration, attested releases on PyPI, documentation.

The fixes of the 1.1.0 bugs found while porting are listed in the commits that make
them. The Java, JavaScript and Lua front ends of the original are out of scope until
the Python one is done.
