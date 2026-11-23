# Local release verification

Run from `IAmGodTranslator_Render_Deploy` with the repository's website and desktop requirements installed in the same Python 3.12 environment. The runner uses Git, Node, and a POSIX host with `/tmp`. Regression browser checks also need the **Node** Playwright package and executable Chromium. The Python Playwright dependency alone cannot run the JavaScript smoke script.

```sh
python tools/verify_release.py run --profile fast \
  --expect-sha <expected-full-commit-sha> --output /tmp/iagt-fast
python tools/verify_release.py run --profile regression \
  --expect-sha <expected-full-commit-sha> --output /tmp/iagt-regression
python tools/verify_release.py check-evidence /tmp/iagt-regression.zip \
  --expect-sha <expected-full-commit-sha>
```

Choose a fresh output directory outside the checkout. The runner creates the directory and a sibling ZIP. Provide `--node-modules /path/to/node_modules` for an external Playwright installation. Use `--chromium /path/to/chromium` or `--node /path/to/node` to select specific executables. The runner does not install packages or browsers.

- **Fast** runs FastAPI startup and route fixtures, browser JavaScript syntax, and the Desktop Companion foundation suite. The opt-in public website test and browser smoke are skipped.
- **Regression** adds translation scheduler, performance and selector fixtures, content import, backup manifest, website/desktop integration, MiniSearch, Reader performance fixtures, and the existing five-viewport browser smoke. The browser launches a fresh loopback server and uses synthetic novel content with a temporary SQLite database. It records the desktop and mobile Home screenshots on disk.
- The selected checks come from the fixed profile in the runner. Missing required scripts fail preflight before any selected test runs. Missing runtime prerequisites leave affected checks unverified. A browser assertion or other nonzero test exit fails the run.

By default the runner exports the committed Git tree from `HEAD` to a temporary directory. For pre-commit verification, stage the proposed files and add `--staged`. The manifest then records both the expected base commit and the exact staged **tree**. To carry the result forward after committing, compare the new commit's tree using `git rev-parse HEAD^{tree}`. Untracked and unstaged files are outside either snapshot. The running verifier must match the selected tree.

The manifest records source identity, selected checks, installed Python distributions, Node and browser versions when available, commands, working directories, fixture environment, timestamps, exit codes, and SHA-256 attachment hashes. The ZIP contains the manifest, summary, raw test streams, and approved browser screenshots. The fixture environment omits ambient credentials, home configuration, and database bindings. The archive excludes the exported checkout, fixture databases, browser profiles, historical artifacts, and local configuration. Use vetted Git revisions and tool installations. Raw diagnostics can contain absolute tool paths, so use neutral installation paths when preparing evidence for external distribution.

Run exit codes are **0 PASS**, **1 FAIL**, and **2 UNVERIFIED**. `SKIPPED` records out-of-profile browser coverage and the desktop suite's opted-out live check. `check-evidence` works on either the ZIP or its unmodified directory and returns success for intact evidence of any result, including a failed run. It checks the manifest digest, required profile membership, expected attachment set, and each attachment's hash. These checks detect omissions and corruption. They are unsigned, so establish provenance independently and use the verifier version that produced the evidence.

Run the isolated controls from the website directory.

```sh
python -m unittest discover -s tools -p test_verify_release.py -v
```

This workflow covers local engineering verification. PostgreSQL release gates, live credentials or providers, production connectivity, and formal release acceptance require their own authorized workflows. Existing historical QA reports remain the record for their original source revisions.
