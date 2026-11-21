def plural(count: int, word: str) -> str:
    """Returns word as is for a count of 1, with an s appended otherwise."""
    return word if count == 1 else f"{word}s"
