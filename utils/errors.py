# Excluded from reload_shared_modules() to keep isinstance checks in error_handler.py
# stable across independent cog reloads. Edits here need a full bot restart.
class UserError(Exception):
    """Raised for expected, user-facing validation failures. Caught by the global
    app-command error handler and shown as an error embed, never logged as a bug."""
