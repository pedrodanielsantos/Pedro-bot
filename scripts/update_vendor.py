"""Downloads the browser libraries the dashboard serves from static/vendor/.

Run after changing a pinned version in utils/vendor.py:

    python scripts/update_vendor.py

Writes each pinned library under its versioned filename and names any older
copies left behind, which belong in the same commit as the bump. Safe to re-run:
existing files are kept unless --force is passed.
"""

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.vendor import VENDORED

VENDOR_DIR = REPO_ROOT / "static" / "vendor"


def download(url: str, destination: Path) -> None:
    with urllib.request.urlopen(url, timeout=30) as response:
        destination.write_bytes(response.read())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download files that already exist")
    args = parser.parse_args()

    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    wanted = set()

    # The license is fetched with the library, not as an afterthought: ansi_up is
    # MIT and its built file carries no notice, so the two have to travel together.
    for lib in VENDORED:
        for name, url in ((lib.local_name, lib.download_url),
                          (lib.local_license_name, lib.license_url)):
            wanted.add(name)
            destination = VENDOR_DIR / name
            if destination.exists() and not args.force:
                print(f"  kept     {name}")
                continue
            try:
                download(url, destination)
            except (urllib.error.URLError, OSError) as e:
                print(f"  FAILED   {name}: {e}")
                return 1
            print(f"  wrote    {name} ({destination.stat().st_size} bytes)")

    # Left in place rather than deleted: removing a file the running dashboard is
    # still serving would break open tabs mid-session.
    stale = sorted(p.name for p in VENDOR_DIR.iterdir() if p.is_file() and p.name not in wanted)
    if stale:
        print("\nSuperseded, delete with the version bump:")
        for name in stale:
            print(f"  {name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
