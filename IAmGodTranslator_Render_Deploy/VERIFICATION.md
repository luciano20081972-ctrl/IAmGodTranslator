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
- Regression also runs the service-worker event tests and the Python Playwright PWA and offline Reader smokes. They exercise a loopback worker upgrade, origin cache isolation, account-scoped IndexedDB reads, the Settings clear control, and offline chapter reopen. Both browser suites use the selected Chromium executable.
- The worker installs anonymous, validated copies of seven public shell resources. Runtime requests use the network first. On network failure only exact shell paths can use the current cache, including the root document used by hash-based Reader routes. Regenerate its content-derived cache version and asset references with the command below.
- The selected checks come from the fixed profile in the runner. Missing required scripts fail preflight before any selected test runs. Missing runtime prerequisites leave affected checks unverified. A browser assertion or other nonzero test exit fails the run.

By default the runner exports the committed Git tree from `HEAD` to a temporary directory. For pre-commit verification, stage the proposed files and add `--staged`. The manifest then records both the expected base commit and the exact staged **tree**. To carry the result forward after committing, compare the new commit's tree using `git rev-parse HEAD^{tree}`. Untracked and unstaged files are outside either snapshot. The running verifier must match the selected tree.

The manifest records source identity, selected checks, installed Python distributions, Node and browser versions when available, commands, working directories, fixture environment, timestamps, exit codes, and SHA-256 attachment hashes. The ZIP contains the manifest, summary, raw test streams, and approved browser screenshots. The fixture environment omits ambient credentials, home configuration, and database bindings. The archive excludes the exported checkout, fixture databases, browser profiles, historical artifacts, and local configuration. Use vetted Git revisions and tool installations. Raw diagnostics can contain absolute tool paths, so use neutral installation paths when preparing evidence for external distribution.

Run exit codes are **0 PASS**, **1 FAIL**, and **2 UNVERIFIED**. `SKIPPED` records out-of-profile browser coverage and the desktop suite's opted-out live check. `check-evidence` works on either the ZIP or its unmodified directory and returns success for intact evidence of any result, including a failed run. It checks the manifest digest, required profile membership, expected attachment set, and each attachment's hash. These checks detect omissions and corruption. They are unsigned, so establish provenance independently and use the verifier version that produced the evidence.

Run the isolated controls from the website directory.

```sh
python -m unittest discover -s tools -p test_verify_release.py -v
```

This workflow covers local engineering verification. PostgreSQL release gates, live credentials or providers, production connectivity, and formal release acceptance require their own authorized workflows. Existing historical QA reports remain the record for their original source revisions.

## Frontend identity

From the website directory run `python tools/frontend_build.py` to verify the checkout. After intentionally changing a shell input, run `python tools/frontend_build.py --write`, review the generated diff, and rerun verification. Generation uses Python's standard library and local files. The regression profile includes this check, its mutation tests, registry validation, and browser checks for both unavailable and altered SDK bytes.

| Identity | Meaning and verification |
| --- | --- |
| Source commit | Git history identity. Supply an independently expected commit to the runner with `--expect-sha`. |
| Source tree | Git identity of the committed or staged files. Supply `--expect-tree` to both `run` and `check-evidence`. After pre-commit qualification compare `git rev-parse 'HEAD^{tree}'` with the recorded tree. |
| Asset digest | SHA-256 of each served shell resource. Application JS and CSS URLs carry their digest. Browser script/style tags and anonymous worker installation fetches enforce Subresource Integrity (SRI). |
| Frontend build | `config/frontend_build_id` hashes the worker logic, canonical URL/MIME/digest inventory and pinned SDK provenance. The hash input omits the derived cache name. HTML, JS, CSS, icon, vendor files and the manifest contribute through their byte digests. Multiple commits with identical frontend inputs can share this identity. |
| Deployment | Compare `/api/health`'s `frontend_build_id` with the qualified result. `deployment_source_commit` comes from Render's `RENDER_GIT_COMMIT`. The optional non-secret `IAGT_DEPLOYMENT_ID` labels one rollout. Missing environment values produce JSON null. The existing `build_marker` still accepts its operator override. Host labels alone do not verify the served bytes. |

A mixed rollout can temporarily block a changed asset or worker installation on an integrity mismatch. Publish the HTML, worker, manifest, ID file and static assets together. A failed installation leaves the previously active worker in service.

### SDK provenance and rollback

The registry pins the npm tarball URL and SHA-512 integrity. During adoption the tarball matched this digest and the npm registry signature over the package name, version and integrity verified with registry key `SHA256:DhQ8wR5APBvFHLF/+Tc+AYvPOdTpcIDqOhxsBHRwC7U`. The committed UMD script is the unmodified `package/dist/umd/supabase.js` member. The browser loads it locally. Existing authenticated requests still use the configured Supabase service. A disposable npm lock resolved the declared dependency graph for license review and an advisory check; npm reported zero known vulnerabilities at review time.

To review a future SDK change, fetch the exact registry metadata and tarball, verify its npm integrity and registry signature, and compare the extracted UMD and license bytes to the proposed files. Refresh third-party notices, the registry and the generated shell together. Run the negative controls and the full profile. Roll back a dependency change by restoring a previously qualified SDK, registry record, notices and matching shell artifacts as one revision. A full rollback to A2.1 also restores its floating jsDelivr reference and external script request.

### Supply-chain inventory

- The website requirements specify ranges for FastAPI, Uvicorn with extras, python-dotenv, psycopg with binary extras, and requests. python-multipart and openai have lower bounds only.
- Desktop requirements specify ranges for customtkinter, requests, beautifulsoup4, and Playwright. The Playwright browser and the Node tooling used by QA also have independent versions.
- Render pins Python 3.12.7 and installs from the website requirements. Both Python lists lack transitive locks and artifact hashes, so a later install can select different versions or platform wheels. The A1 manifest records what each run installed. Weekly Dependabot checks cover both lists.
- A2.3 follow-up: generate and validate platform-specific Python locks with hashes, record toolchain and browser versions in CI, and connect source/tree and frontend identity verification to release gates. This package makes no Python dependency upgrades.
