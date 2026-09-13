"""The browser libraries the dashboard serves itself from static/vendor/.

Pinned on purpose. Serving them locally keeps the dashboard working with no
internet, which is when you are most likely to be looking at it, and pinning
means an upstream release cannot change what runs without a commit.

check_for_updates() only reports. Downloading is scripts/update_vendor.py, run
deliberately, the same way scripts/setup_lavalink.py handles the node's jars.
"""

import asyncio
import logging
from typing import NamedTuple

import aiohttp

logger = logging.getLogger("vendor")

REGISTRY = "https://registry.npmjs.org"
CDN = "https://unpkg.com"

# Seconds any one registry request may take, and so roughly the whole check,
# since they run concurrently. Short because nothing waits on it and a missed
# check costs nothing.
CHECK_TIMEOUT = 5.0


class Library(NamedTuple):
    package: str       # npm package name
    version: str       # pinned; bump here, then run scripts/update_vendor.py
    path: str          # file to take from inside the package
    filename: str      # local name, with the version substituted in
    license_path: str  # license file inside the package, fetched alongside

    @property
    def local_name(self) -> str:
        return self.filename.format(version=self.version)

    @property
    def local_license_name(self) -> str:
        # Cut after the version, not at the first dot, or a name carrying both a
        # dotted version and a compound extension loses most of itself.
        end = self.local_name.index(self.version) + len(self.version)
        return f"{self.local_name[:end]}.LICENSE"

    @property
    def download_url(self) -> str:
        return f"{CDN}/{self.package}@{self.version}/{self.path}"

    @property
    def license_url(self) -> str:
        return f"{CDN}/{self.package}@{self.version}/{self.license_path}"


# The version is part of the local filename, so an upgrade is a new URL and no
# browser can keep serving a stale copy of the old one.
#
# Each license is vendored next to its library. ansi_up is MIT, which requires
# the notice to travel with the code, and the built file carries none of its own.
# htmx is 0BSD and requires nothing, but is kept alongside for consistency.
VENDORED = (
    Library("htmx.org", "2.0.10", "dist/htmx.min.js", "htmx-{version}.min.js", "LICENSE"),
    Library("ansi_up", "6.0.6", "ansi_up.js", "ansi_up-{version}.js", "LICENSE"),
)


def static_urls() -> dict[str, str]:
    """Package name -> the URL the dashboard serves it at, for the templates."""
    return {lib.package: f"/static/vendor/{lib.local_name}" for lib in VENDORED}


def _is_newer(latest: str, pinned: str) -> bool:
    """Whether latest sorts above pinned. Compares the numeric parts only, so a
    prerelease suffix is ignored rather than mis-sorted."""
    def parts(version: str) -> tuple[int, ...]:
        return tuple(int(p) for p in version.split("-")[0].split(".") if p.isdigit())

    return parts(latest) > parts(pinned)


async def _latest(session: aiohttp.ClientSession, lib: Library) -> str:
    # /latest is the one release, ~1.5KB. The full packument is the whole
    # release history, which for htmx is over 200KB.
    async with session.get(f"{REGISTRY}/{lib.package}/latest") as resp:
        resp.raise_for_status()
        return (await resp.json())["version"]


async def check_for_updates() -> None:
    """Logs any vendored library with a newer release. Never raises and never
    writes: a registry it can't reach is not worth interrupting startup for, and
    upgrading stays a decision.

    Reports across majors too, so staying on an old major deliberately means
    living with the notice until the pin is moved.
    """
    try:
        timeout = aiohttp.ClientTimeout(total=CHECK_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            found = await asyncio.gather(
                *(_latest(session, lib) for lib in VENDORED), return_exceptions=True
            )
    except Exception:
        # Offline, DNS down, registry unreachable. Nothing depends on this.
        return

    for lib, latest in zip(VENDORED, found):
        if isinstance(latest, str) and _is_newer(latest, lib.version):
            logger.warning(f"{lib.package} {latest} is available (vendored {lib.version})")
