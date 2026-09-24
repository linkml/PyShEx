# Contract tests

These tests pin down what PyShEx promises to the code that depends on it.
They are self-contained (no network, no files outside this directory),
so CI also runs them against the built wheel before a release is published.

| File | What it protects |
|---|---|
| `test_public_api.py` | Signatures, exports and CLI options of the public API. |
| `test_client_linkml.py` | The call patterns [linkml](https://github.com/linkml/linkml) uses. |
| `test_client_jupyter_rdfify.py` | The call patterns [jupyter-rdfify](https://pypi.org/project/jupyter-rdfify/) 1.0.4 uses. |
| `test_downstream_packages.py` | The real downstream packages, when they are installed (CI `downstream` job). |

## When a test here fails

A failure means a PyPI release built from this tree could break existing users.

* If the change was accidental, fix the code, not the test.
* If the break is intentional, bump the version accordingly
  (major, or minor while PyShEx is < 1.0), record it in `ChangeLog`,
  and update the expectation in the same pull request so reviewers see it.

Adding new optional parameters at the end of a signature, or exporting new names,
is compatible and does not require changing these tests.

## Other clients on PyPI

The PyPI project `ontology` (0.1.0) appears in a search for PyShEx but is an empty
placeholder with no dependencies, so it imposes no constraints.
