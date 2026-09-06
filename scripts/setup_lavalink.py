"""Installs the Lavalink node the music cogs talk to.

Run once on the host that runs the bot:

    python scripts/setup_lavalink.py

Downloads pinned Lavalink and plugin jars, renders application.yml from
config/lavalink/application.yml.example, and prints the .env lines to add.
Safe to re-run: existing files are kept unless --force is passed.

The install dir lives on local disk, never on the network drive the repo sits
on. Lavalink writes logs and plugin state next to its jar, and a JVM started
over SMB is slow to boot and prone to file locking problems.
"""

import argparse
import os
import secrets
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

LAVALINK_VERSION = "4.2.2"
LAVASRC_VERSION = "4.8.3"

# youtube-plugin is not downloaded here. application.yml declares it as a
# snapshot dependency so Lavalink fetches it itself, because tagged releases
# lag behind YouTube's extraction changes. See the note in the config template.

MIN_JAVA_VERSION = 17

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_TEMPLATE = REPO_ROOT / "config" / "lavalink" / "application.yml.example"

# (url, destination relative to the install dir)
DOWNLOADS = [
    (
        f"https://github.com/lavalink-devs/Lavalink/releases/download/{LAVALINK_VERSION}/Lavalink.jar",
        "Lavalink.jar",
    ),
    (
        f"https://github.com/topi314/LavaSrc/releases/download/{LAVASRC_VERSION}"
        f"/lavasrc-plugin-{LAVASRC_VERSION}.jar",
        f"plugins/lavasrc-plugin-{LAVASRC_VERSION}.jar",
    ),
]


def default_install_dir() -> Path:
    if sys.platform == "win32":
        # The trailing separator matters: Path("C:") / "lavalink" is the
        # drive-relative "C:lavalink", not the root-anchored "C:\lavalink".
        drive = os.environ.get("SystemDrive", "C:")
        return Path(f"{drive}\\") / "lavalink"
    return Path("/opt/lavalink")


def check_java() -> str | None:
    """The detected java version string, or None if it's missing or too old."""
    java = shutil.which("java")
    if not java:
        print("  java not found on PATH.")
        return None

    # `java -version` writes to stderr on every version still in the wild.
    result = subprocess.run([java, "-version"], capture_output=True, text=True)
    first_line = (result.stderr or result.stdout).splitlines()[0] if (result.stderr or result.stdout) else ""

    try:
        # e.g. openjdk version "21.0.5" 2024-10-15
        version = first_line.split('"')[1]
        # Java 9+ reports 21.0.5, Java 8 and older report 1.8.0_x.
        major = int(version.split(".")[1] if version.startswith("1.") else version.split(".")[0])
    except (IndexError, ValueError):
        print(f"  Could not parse the java version from: {first_line!r}")
        return None

    if major < MIN_JAVA_VERSION:
        print(f"  Found Java {major} at {java}, but Lavalink {LAVALINK_VERSION} needs {MIN_JAVA_VERSION}+.")
        return None

    print(f"  Java {major} at {java}")
    return version


def download(url: str, destination: Path, force: bool):
    if destination.exists() and not force:
        print(f"  Kept  {destination.name} (already present)")
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    # Downloaded to a temp name first so an interrupted run can't leave a
    # truncated jar in place that looks valid to the next one.
    temp = destination.with_suffix(destination.suffix + ".part")

    print(f"  Fetch {destination.name} ... ", end="", flush=True)
    try:
        with urllib.request.urlopen(url) as response, open(temp, "wb") as f:
            shutil.copyfileobj(response, f)
    except urllib.error.HTTPError as e:
        temp.unlink(missing_ok=True)
        raise SystemExit(f"failed ({e.code} {e.reason})\n  URL: {url}")
    except urllib.error.URLError as e:
        temp.unlink(missing_ok=True)
        raise SystemExit(f"failed ({e.reason})\n  URL: {url}")

    # A jar is a zip. Catches an HTML error page saved under a .jar name.
    if not zipfile.is_zipfile(temp):
        temp.unlink(missing_ok=True)
        raise SystemExit(f"failed (not a valid jar)\n  URL: {url}")

    temp.replace(destination)
    print(f"ok ({destination.stat().st_size // 1024} KiB)")


def write_config(install_dir: Path, force: bool) -> str | None:
    """Renders application.yml. Returns the password, or None if one already existed."""
    config = install_dir / "application.yml"

    if config.exists() and not force:
        print("  Kept  application.yml (already present, password left alone)")
        return None

    if not CONFIG_TEMPLATE.exists():
        raise SystemExit(f"Template not found: {CONFIG_TEMPLATE}")

    password = secrets.token_urlsafe(32)
    config.write_text(
        CONFIG_TEMPLATE.read_text(encoding="utf-8").replace("__PASSWORD__", password),
        encoding="utf-8",
    )
    print("  Wrote application.yml with a freshly generated password")
    return password


def main():
    parser = argparse.ArgumentParser(description="Install the Lavalink node for the music cogs.")
    parser.add_argument(
        "--dir", type=Path, default=None,
        help=f"Install directory (default: {default_install_dir()})",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-download jars and regenerate application.yml, replacing what's there",
    )
    args = parser.parse_args()

    install_dir = (args.dir or default_install_dir()).resolve()

    print(f"Installing Lavalink {LAVALINK_VERSION} into {install_dir}\n")

    print("Checking Java:")
    if not check_java():
        raise SystemExit(
            f"\nInstall a JDK {MIN_JAVA_VERSION}+ first, then re-run this script.\n"
            "  Windows: winget install EclipseAdoptium.Temurin.21.JDK\n"
            "  Debian/Ubuntu: sudo apt install openjdk-21-jre-headless\n"
            "  Fedora: sudo dnf install java-21-openjdk-headless"
        )

    try:
        install_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise SystemExit(
            f"\nNo permission to create {install_dir}.\n"
            "Re-run elevated, or pick a writable location with --dir."
        )

    print("\nDownloading:")
    for url, relative in DOWNLOADS:
        download(url, install_dir / relative, args.force)

    print("\nConfig:")
    password = write_config(install_dir, args.force)

    print("\n" + "=" * 60)
    print("Done. Add these to your .env:\n")
    print(f"LAVALINK_DIR={install_dir}")
    print("LAVALINK_URI=http://127.0.0.1:2333")
    if password:
        print(f"LAVALINK_PASSWORD={password}")
    else:
        print("LAVALINK_PASSWORD=<the password already in application.yml>")
    print("\nThen restart the bot. run.py starts the node automatically.")
    print("=" * 60)


if __name__ == "__main__":
    main()
