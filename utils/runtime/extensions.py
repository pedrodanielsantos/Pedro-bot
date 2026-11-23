import importlib
import os
import sys

# Modules cogs import from but that aren't extensions themselves (no setup()),
# so bot.reload_extension()/load_extension() never touches them and they'd
# otherwise stay stale in sys.modules until the whole process restarts.
_SHARED_MODULES = ("config", "db", "utils")
_SHARED_MODULE_PREFIXES = tuple(f"{name}." for name in _SHARED_MODULES)


def reload_shared_modules():
    """Reloads db/config/utils/mixins modules so a cog reload picks up fresh
    dependency code instead of whatever was cached at process startup."""
    for name in sorted(sys.modules):
        if name in _SHARED_MODULES or name.startswith(_SHARED_MODULE_PREFIXES):
            if name == "utils.errors":
                # UserError is isinstance-checked from error_handler.py, which may not be
                # reloaded in the same pass; reloading this module would mint a new class
                # and break that check.
                continue

            module = sys.modules[name]
            if name == "db.database":
                # module-level `db` holds the live aiosqlite connection singleton,
                # set once by initialize_databases(). A reload re-executes the file
                # top to bottom and would reset it to None, breaking every cog's DB
                # access until a full process restart, so carry it across the reload.
                live_connection = getattr(module, "db", None)
                importlib.reload(module)
                module.db = live_connection
            else:
                importlib.reload(module)


def _has_setup_entrypoint(file_path: str) -> bool:
    with open(file_path, encoding="utf-8") as f:
        return "def setup(" in f.read()


def discover_cog_paths(cogs_dir: str) -> list[str]:
    paths = []
    for root, dirs, files in os.walk(cogs_dir):
        for filename in files:
            if filename.endswith(".py") and not filename.startswith("__"):
                if not _has_setup_entrypoint(os.path.join(root, filename)):
                    continue
                relative_path = os.path.relpath(root, cogs_dir)
                if relative_path == ".":
                    paths.append(f"cogs.{filename[:-3]}")
                else:
                    paths.append(f"cogs.{relative_path.replace(os.sep, '.')}.{filename[:-3]}")
    return paths
