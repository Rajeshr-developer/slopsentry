# Releasing

1. **Bump the version in both places, together:**
   - `pyproject.toml` → `[project] version`
   - `npm/package.json` → `version`

   They must match. The npm wrapper runs `uvx slopsentry@<its own version>`, so an npm
   release whose version isn't on PyPI fails for every user.
2. Run `pytest` and `ruff check`, and confirm CI is green on `main`.
3. Build and check locally: `python -m build` and `twine check --strict dist/*`.
4. Publish to TestPyPI: run the **Publish** workflow manually (Actions → Publish → Run
   workflow, or `gh workflow run publish.yml`). Then install it into a fresh venv:

   ```sh
   pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ slopsentry==X.Y.Z
   slopsentry check requests
   ```

5. Tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`. The Publish workflow checks
   the tag matches `pyproject.toml` and publishes to PyPI.
6. Once the version is live on PyPI, publish the npm wrapper: `cd npm && npm publish`.
   Check it with `npx slopsentry@X.Y.Z check requests`.

Trusted Publishing is configured on pypi.org and test.pypi.org for this repo, workflow
`publish.yml`, with environments `pypi` and `testpypi`.
