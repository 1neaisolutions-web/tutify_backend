"""Text cleanup for PostgreSQL string columns (rejects NUL / U+0000)."""


def sanitize_pg_text(value: str | None) -> str:
    """Strip characters PostgreSQL rejects in text/varchar (notably \\x00)."""
    if not value:
        return ""
    return value.replace("\x00", "")
