# vaillant-plus-cn-api
Python package for interacting with Vaillant devices sold in China mainland through APIs in Vaillant plus app.

## Releasing

Releases are published to PyPI by the `Publish` workflow, which runs when a
GitHub release is published. Authentication uses PyPI Trusted Publishing
(OIDC), so there is no API token in this repository.

1. Bump `version` in `pyproject.toml` and merge it to `main`.
2. Create a GitHub release whose tag is that version prefixed with `v`
   (`2.0.1` → `v2.0.1`).
3. The workflow runs the tests, refuses to continue if the tag and the
   version in `pyproject.toml` disagree, builds the distributions and
   uploads them to PyPI.

Running the workflow manually from the Actions tab builds and checks the
distributions without uploading anything, which is a useful dry run before
tagging.

### One-time PyPI setup

Trusted publishing has to be configured once, on
<https://pypi.org/manage/project/vaillant-plus-cn-api/settings/publishing/>:

| Field | Value |
| --- | --- |
| Owner | `daxingplay` |
| Repository name | `vaillant-plus-cn-api` |
| Workflow name | `publish.yaml` |
| Environment name | `pypi` |

Until that is configured the upload step fails with an OIDC error; nothing
else in the workflow depends on it.
