"""Require the installed qualification distributions to match the exact lock."""
import argparse
import importlib.metadata
from pathlib import Path
import re
import subprocess
import sys

QUALIFICATION = Path(__file__).resolve().parent
ROOT = QUALIFICATION.parents[1]
LOCK = QUALIFICATION / "python-linux-x86_64-cp312.lock"
ENTRY = re.compile(r"([a-z0-9-]+)==([^\s]+) --hash=sha256:[a-f0-9]{64}")


def canonical(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def verify(lock):
    expected = {}
    for line in lock.read_text(encoding="ascii").splitlines():
        if not line or line.startswith("#"):
            continue
        entry = ENTRY.fullmatch(line)
        if not entry or entry[1] in expected:
            raise ValueError(f"invalid or duplicate lock entry: {line}")
        expected[entry[1]] = entry[2]
    installed = {
        canonical(package.metadata["Name"]): package.version
        for package in importlib.metadata.distributions()
        if canonical(package.metadata["Name"]) != "pip"
    }
    if not expected or expected != installed:
        differences = [name for name in sorted(expected.keys() | installed.keys())
                       if expected.get(name) != installed.get(name)]
        raise ValueError(f"installed dependency identity mismatch: {', '.join(differences)}")
    print(f"Exact lock identity verified for {len(expected)} distributions.", flush=True)
    pip = [sys.executable, "-m", "pip", "--isolated", "--disable-pip-version-check"]
    subprocess.run([*pip, "check"], check=True)
    subprocess.run([
        *pip, "install", "--dry-run", "--no-index",
        "-r", str(ROOT / "IAmGodTranslator_Render_Deploy/requirements.txt"),
        "-r", str(ROOT / "GodTranslator_Desktop_Companion/requirements.txt"),
    ], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=LOCK)
    try:
        verify(parser.parse_args().lock)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
