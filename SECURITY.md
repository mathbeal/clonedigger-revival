# Security

## Scope

Clone Digger reads Python source files and prints a report. What it does, and does not:

- it **never runs the code it reads**: each file is parsed with `ast.parse`, nothing is
  imported, compiled to bytecode or evaluated;
- it opens **no network connection**, and has no dependency to fetch at run time;
- it reads only the files and directories named on the command line, and writes only to
  its standard output and standard error;
- the HTML report escapes every piece of code and every path it shows, so that code
  read from a file cannot add markup or a script to the page; the JSON and SARIF reports
  are written with Python's `json` module.

The code it reads is untrusted input. A file written to exhaust time or memory (very
deep nesting, very long runs of similar statements) can make a run slow or fail; it
cannot make the tool do anything else. Such a report is welcome, as a bug, unless it
crashes the interpreter.

## Reporting a vulnerability

Open a [security advisory](https://github.com/mathbeal/clonedigger-revival/security/advisories/new).
Please do not open a public issue for a vulnerability.

Expect a first answer within a week. The report is reproduced, fixed with a test in the
advisory's private fork, released, then disclosed, with credit to the reporter unless
they ask to stay anonymous.

## Supported versions

No version is released yet: the `main` branch only.

## How the code is kept safe

- the dependencies of the tools that check and build it are locked with hashes in
  `uv.lock`, and audited by pip-audit on every change;
- the actions of the workflows are pinned by commit, start with no permission, and are
  audited by zizmor; every commit is scanned for secrets by gitleaks;
- ruff's security rules (bandit) fail the build on a risky call; CodeQL scans the code
  once the repository is public;
- the build is reproducible: the same commit gives the same wheel and sdist, bit for bit
  (`just reproducible`);
- every build writes a CycloneDX SBOM of the installed wheel (`just build`), attached as
  an artifact of the CI and release workflows.
