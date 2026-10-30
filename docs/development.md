# Development and reproduction

From a clone, create a virtual environment and install the test dependencies:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install '.[test]'
.venv/bin/python -m pytest -q
```

Regenerate the public fixtures:

```sh
python3 scripts/make_fixtures.py examples
```

The files contain Alpha, Beta, Gamma and Delta, each with a newline. Only Alpha and Gamma gain ` revised`; only Beta and Gamma move their declared date from 2026-10-29 to 2026-10-30.

```sh
lastmod-ledger compare examples/before.json examples/after.json
```

Expected exit 1: four compared URLs, two review candidates and one pair in each quadrant.

```sh
lastmod-ledger compare examples/before.json examples/coverage.json --json
```

Expected exit 2: the same four quadrants and two review candidates, plus two added URLs. Epsilon has a file; Missing has a declared mapping but no file. Neither added URL becomes a two-sided byte/date comparison.

The deliberately small independent reference supports only the four complete fixture pairs:

```sh
python3 scripts/reference.py examples/before.json examples/after.json
```

It prints one URL per quadrant and their counts. It is not the hardened production parser and should only be run on these trusted fixtures.

To record the terminal demo, install VHS and its dependencies, install the package into your current environment, then run from the repository root:

```sh
vhs docs/demo.tape
```

The tape executes the CLI, showing the four pairs followed by the incomplete coverage run. It does not regenerate either sitemap. Fixtures are checked in so a recording cannot quietly replace the inputs it is reviewing.
