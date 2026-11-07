# Sending the SARIF report to GitHub code scanning

`--format sarif` writes a
[SARIF 2.1.0](https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html) log, the
format GitHub code scanning reads. Uploaded, each clone becomes an alert on the Security
tab of the repository, on the lines of its first copy, with the second copy linked
beside it as a related location.

This page is the workflow that does it, and what each part of it is for.

## The workflow

[`examples/code-scanning.yml`](../examples/code-scanning.yml), to copy into
`.github/workflows/` of a project:

```yaml
name: duplicated code

on:
  push:
    branches: [main]
  pull_request:

# No job may do anything until it says so.
permissions: {}

# A new push to a pull request makes the previous run obsolete.
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

jobs:
  clonedigger:
    name: clone digger, to code scanning
    runs-on: ubuntu-latest
    timeout-minutes: 15
    permissions:
      contents: read          # check the code out
      security-events: write  # upload the SARIF report
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
      - name: find duplicated code
        # No release is tagged yet: until there is one, write the hash of a commit of
        # this repository in place of v0.1.0, or the job stops at the install.
        # The status 1 says clones were found: they are the alerts to upload, not a
        # failure of the job. Any other status, 2 for a file that cannot be read or
        # options that cannot be used, stops it here.
        run: |
          uvx --from 'git+https://github.com/mathbeal/clonedigger-revival@v0.1.0' \
            clonedigger src --format sarif > clonedigger.sarif || [ "$?" -eq 1 ]
      - uses: github/codeql-action/upload-sarif@9b3254085494b55a0f7c4c2b3d2d52cc712ce370 # v4.39.1
        with:
          sarif_file: clonedigger.sarif
          category: clonedigger
```

Three things to change: `src`, the paths to read; `v0.1.0`, the revision of this
repository to install, which is a tag of a release once there is one and the hash of a
commit until then, because no release is tagged today (publishing is the last step of
the [roadmap](../ROADMAP.md)); and the thresholds, if the defaults are not the ones
wanted. They can be written once in the
project's own `pyproject.toml`, under `[tool.clonedigger]`, instead of in the command
line here: see the [README](../README.md#written-down-in-pyprojecttoml).

## What each part is for

**The permissions.** `permissions: {}` at the top takes everything away, so a job holds
only what it is given back. This one needs two things and asks for nothing else:
`contents: read` to check the code out, and `security-events: write` to upload the
report, which is the one permission code scanning requires
([GitHub documentation](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/integrate-with-existing-tools/upload-sarif-file)).
`persist-credentials: false` keeps the checkout from leaving the token in
`.git/config`, where any later step could read it. A private repository is a case of
its own, at the end of this page.

**The actions, pinned by their commit.** Each `uses:` names a 40-character commit hash,
with the version it stood for in the comment beside it. A tag can be moved to another
commit; a hash cannot, so what runs is what was read. The comment is what
[Renovate](https://docs.renovatebot.com) and Dependabot rewrite when they raise the
version, which is how the pin stays current.

**The exit status.** The command answers 1 when it finds clones, which is the ordinary
case here: the alerts are the point of the run, so the step accepts that one status and
lets the SARIF be uploaded. It answers 2 when a file cannot be read or the options
written down cannot be used, and the job stops there rather than uploading a report that
means nothing. This is the same `|| [ "$?" -eq 1 ]` the `just examples` recipe of this
repository uses.

**`category: clonedigger`.** The category keeps one tool's alerts apart from another's
on the same commit, so a project uploading CodeQL and this tool sees two sets of results
instead of each run closing the other's alerts.

## What an alert holds

The committed [`examples/report.sarif`](../examples/report.sarif), written from
[`examples/shipping.py`](../examples/shipping.py) by `just examples`, is what gets
uploaded. Each clone is one result:

```json
{
  "ruleId": "duplicated-code",
  "level": "warning",
  "message": {
    "text": "Lines 46-54 are a copy of [examples/shipping.py:35-43](1), up to a difference of 4."
  },
  "locations": [...],
  "relatedLocations": [...]
}
```

The alert sits on lines 46 to 54, the first copy, under the single rule
`duplicated-code` at the `warning` level. The second copy is a related location, which
GitHub shows as the link in the message, so one alert is raised for the pair rather than
two facing each other. "Up to a difference of 4" is the distance: how many names,
constants or subtrees one copy would have to change to become the other.

## How many alerts to expect

GitHub rejects a SARIF file whose run holds more than 25,000 results, and displays the
top 5,000 of the results it accepts
([the limits](https://docs.github.com/en/code-security/reference/code-scanning/sarif-files/sarif-support)).
A pair is a result, and pairs grow fast with families of copies: in the comparison of
the [README](../README.md#compared-with-line-and-token-tools), measured by
`just compare`, SQLAlchemy 2.1.4 reports 5,341 pairs and Django 6.1.2 5,166, both over
the 5,000 displayed. A project of that size raises `--size-threshold`, lowers
`--distance-threshold`, or points the command at one package rather than the whole
tree.

A clone is reported on every run, so an alert that stays open is a copy still there, and
one fixed is closed by the next run on the same branch.

On a private or internal repository, code scanning works once GitHub Code Security is
enabled for it
([GitHub documentation](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/integrate-with-existing-tools/upload-sarif-file));
on a public repository there is nothing to enable.

Its two sources do not ask for the same permissions there, so both are given here. The
example workflow of that page adds `actions: read`, "only required for workflows in
private repositories". The README of the upload action at the version pinned above
asks for less: "All advanced setup code scanning workflows must have the
`security-events: write` permission. Workflows in private repositories must
additionally have the `contents: read` permission."
([README of the action](https://github.com/github/codeql-action/blob/v4.39.1/README.md#workflow-permissions)).
The job above holds those two, which is what the action says it needs; a private
repository where the upload is refused is the case to add `actions: read` in.

## What is checked here

- The workflow above is `examples/code-scanning.yml` byte for byte, and every claim this
  page makes about it, its pinned hashes, its two permissions and the paths it writes
  and uploads, is checked by `tests/test_code_scanning.py`.
- [zizmor](https://docs.zizmor.sh) audits it under `just hygiene` and in CI, with
  `--persona=auditor`, the strictest it has, and reports nothing on it.
- The SARIF the tool writes validates against the OASIS 2.1.0 schema, with clones and
  without, in `tests/test_report.py`, against the schema committed in
  `tests/data/sarif-schema-2.1.0.json`.
