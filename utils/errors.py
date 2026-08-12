class UserError(Exception):
    """Raised for expected, user-facing validation failures. Caught by the global
    app-command error handler and shown as an error embed, never logged as a bug."""
