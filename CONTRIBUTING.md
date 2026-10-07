# Contributing

Thank you for helping bring Clone Digger back. Two rules come before the others.

**Credit the original.** Clone Digger is Peter Bulychev's work, and its algorithm is his
and Marius Minea's. A file ported from the 1.1.0 release keeps his copyright line and
adds one saying who modified it and when (section 5 of the GPL). The release itself
stays under `legacy/`, unmodified.

**Stay faithful, and prove it.** A ported function must give the answers the original
gives. Those answers are recorded from the unmodified release, run under Python 2.7
(`just golden`, needs Docker), in `tests/golden/`. A deliberate change of behaviour is
written down in the commit and in the code, with its reason.

## Before every commit

    just check

It runs, in order: formatting and lint (ruff with every rule, pylint, pydoclint for
complete Google docstrings, deptry), `mypy --strict`, the tests at 100 % of lines and
branches, vulture for code that nothing calls, lexdrift for one word per idea, and the
lockfile check. `just hygiene` looks for typos.

Before a release, `just mutate` changes the code one small way at a time and checks
that a test fails each time. Every mutant is killed today; a survivor is a behaviour no
test pins down, or a change that cannot alter any result, marked
`# pragma: no mutate` with the reason.

## Tests

Every test has a docstring that says the behaviour it checks, in one sentence. Prefer a
property (Hypothesis) when the behaviour holds for every input, and a recorded answer of
the original when it is about faithfulness.

## Commits

Conventional commit messages in English, signed off (`git commit -s`): the sign-off
certifies the Developer Certificate of Origin, that you have the right to submit the
change under this licence.
