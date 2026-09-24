#!/usr/bin/env python3
"""Fail when the pyshex API breaks relative to the previous release without a matching version bump.

Uses griffe (https://mkdocstrings.github.io/griffe/) to diff the code against the previous
``v*`` release tag. A breaking change passes only if one of these holds:

* ``--new-version`` bumps the major version, or the minor version while the major is 0;
* ``ALLOW_BREAKING=1`` is set. CI sets it on pull requests labelled ``breaking-change``.

Run it locally with:

    uv run --no-project --with 'griffe>=2,<3' python .github/scripts/api_compat.py
"""
import argparse
import os
import re
import subprocess
import sys


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def previous_release(exclude: str | None) -> str | None:
    tags = git("tag", "--merged", "HEAD", "--sort=-v:refname", "--list", "v[0-9]*").split()
    return next((t for t in tags if t != exclude), None)


def major_minor(version: str) -> tuple[int, int]:
    m = re.match(r"v?(\d+)\.(\d+)", version)
    if not m:
        sys.exit(f"cannot parse version {version!r}")
    return int(m[1]), int(m[2])


def allows_breaking(old: str, new: str) -> bool:
    (old_major, old_minor), (new_major, new_minor) = major_minor(old), major_minor(new)
    return new_major > old_major or (new_major == old_major == 0 and new_minor > old_minor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--new-version", help="version being released, e.g. the release tag v0.10.0")
    parser.add_argument("--against", help="git ref to compare with (default: previous v* tag)")
    args = parser.parse_args()

    against = args.against or previous_release(exclude=args.new_version)
    if against is None:
        print("No previous release tag found; nothing to compare against.")
        return 0

    fmt = "github" if os.environ.get("GITHUB_ACTIONS") else "oneline"
    cmd = [sys.executable, "-m", "griffe", "check", "pyshex", "--search", ".", "--against", against, "--format", fmt]
    print(f"Comparing the pyshex API with {against}", flush=True)
    if subprocess.run(cmd).returncode == 0:
        print("No breaking API changes.")
        return 0

    if args.new_version and allows_breaking(against, args.new_version):
        print(f"Breaking changes accepted: {args.new_version} is a breaking-change release after {against}.")
        return 0
    if os.environ.get("ALLOW_BREAKING") == "1":
        print("Breaking changes accepted because ALLOW_BREAKING=1 (pull request labelled 'breaking-change').")
        return 0
    print(
        f"\nThe changes above break the API released in {against}. Either restore compatibility, or, if the break "
        "is intended, label the pull request 'breaking-change', record it in ChangeLog, and release it as a new "
        "major version (a new minor version while PyShEx is 0.x).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
