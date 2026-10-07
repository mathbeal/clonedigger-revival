# Corpus: real files that Python 2.7 and Python 3 both read

The original Clone Digger reads only Python 2 and the port only Python 3: these files
are written in the common subset, so both can be run on them and their clones compared.
Each was taken unmodified from its release on PyPI, checksum verified, on 2026-10-07:

| File | Release | sdist SHA-256 (start) | Licence |
|---|---|---|---|
| `bottle.py` | bottle 0.12.25 | `e1a9c94970ae6d71` | MIT, Copyright (c) Marcel Hellkamp |
| `six.py` | six 1.16.0 | `1e61c37477a16264` | MIT, Copyright (c) Benjamin Peterson |
| `docopt.py` | docopt 0.6.2 | `49b3a825280bd66b` | MIT, Copyright (c) Vladimir Keleshev |

Each file keeps its own copyright and licence notice. `*.cpd.xml` is the report of the
unmodified Clone Digger 1.1.0 on that file alone, with default thresholds
(`just golden`, needs Docker).
