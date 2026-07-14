import os


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
