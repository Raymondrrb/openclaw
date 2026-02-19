#!/usr/bin/env python3
"""Audit API key file permissions and flag misconfigurations.

Inspired by community hardening guide (jordanlyall/8b9e566c).
Run periodically or before batch jobs to catch permission drift.
"""
import os
import stat
import sys

ENV_DIR = os.path.expanduser("~/.config/newproject")
CONFIG_DIR = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "config")

# Files that should be owner-read/write only (0o600)
EXPECTED_MODE = 0o600
EXPECTED_DIR_MODE = 0o700


def check_permissions(path, expected):
    """Return (ok, actual_mode) for a file or directory."""
    try:
        st = os.stat(path)
    except OSError:
        return None, None
    actual = stat.S_IMODE(st.st_mode)
    return actual == expected, actual


def format_mode(mode):
    return f"{oct(mode)} ({stat.filemode(mode | stat.S_IFREG)})" if mode is not None else "N/A"


def main():
    issues = []
    checked = 0

    # Check env directory permissions
    ok, mode = check_permissions(ENV_DIR, EXPECTED_DIR_MODE)
    if ok is None:
        print(f"  SKIP  {ENV_DIR} (not found)")
    elif not ok:
        issues.append(f"{ENV_DIR} is {format_mode(mode)}, should be {oct(EXPECTED_DIR_MODE)}")
    checked += 1

    # Check each .env file in ~/.config/newproject/
    if os.path.isdir(ENV_DIR):
        for name in sorted(os.listdir(ENV_DIR)):
            if not name.endswith(".env"):
                continue
            path = os.path.join(ENV_DIR, name)
            ok, mode = check_permissions(path, EXPECTED_MODE)
            checked += 1
            if ok is None:
                continue
            if ok:
                print(f"  OK    {path}")
            else:
                issues.append(f"{path} is {format_mode(mode)}, should be {oct(EXPECTED_MODE)}")
                print(f"  WARN  {path} — too permissive ({format_mode(mode)})")

    # Check config/*.env.example should NOT contain real keys
    if os.path.isdir(CONFIG_DIR):
        for name in sorted(os.listdir(CONFIG_DIR)):
            if not name.endswith(".env.example"):
                continue
            path = os.path.join(CONFIG_DIR, name)
            checked += 1
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "=" not in line or line.startswith("#"):
                        continue
                    _, val = line.split("=", 1)
                    val = val.strip()
                    # Flag if value looks like a real key (not a placeholder/URL)
                    is_placeholder = (
                        val.startswith("YOUR_")
                        or val.startswith("your-")
                        or val.startswith("https://")
                        or val.startswith("http://")
                        or val in ("true", "false", "public", "private")
                    )
                    if val and not is_placeholder and len(val) > 20:
                        issues.append(f"{path} may contain a real API key (line: {line[:40]}...)")
                        print(f"  WARN  {path} — possible real key in example file")
                        break
                else:
                    print(f"  OK    {path}")

    print()
    if issues:
        print(f"FOUND {len(issues)} issue(s):")
        for issue in issues:
            print(f"  - {issue}")
        print()
        print("Fix with:")
        print(f"  chmod 700 {ENV_DIR}")
        print(f"  chmod 600 {ENV_DIR}/*.env")
        sys.exit(1)
    else:
        print(f"All clear. Checked {checked} items, no issues found.")


if __name__ == "__main__":
    main()
