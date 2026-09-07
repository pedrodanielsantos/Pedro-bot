def parse_number_spec(
    spec: str, *, noun: str = "number", maximum: int | None = None, limit: int | None = None
) -> list[int]:
    """Parses '12', '10-12' or '4,7,12' into a sorted list of unique numbers.

    Ranges are inclusive and start at 1. noun names what is being counted in the
    error messages, maximum is the largest value accepted, and limit caps how
    many numbers the spec may expand to.
    """
    numbers = set()
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        start, _, end = token.partition("-")
        try:
            start = int(start)
            end = int(end) if end else start
        except ValueError:
            raise ValueError(f"`{token}` isn't a {noun} or range.")
        if start < 1 or end < start:
            raise ValueError(f"`{token}` isn't a valid range.")
        if maximum is not None and end > maximum:
            raise ValueError(f"`{token}` is out of range, the highest is {maximum}.")
        numbers.update(range(start, end + 1))

    if not numbers:
        raise ValueError(f"No {noun}s given.")
    if limit is not None and len(numbers) > limit:
        raise ValueError(f"Too many {noun}s at once, the limit is {limit}.")
    return sorted(numbers)
