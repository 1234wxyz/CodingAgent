import re


def search_pattern(text: str, pattern: str) -> list[int]:
    """Return list of line numbers (1-based) where pattern appears as literal text."""
    matches = []
    for i, line in enumerate(text.splitlines(), 1):
        if re.search(pattern, line):
            matches.append(i)
    return matches
