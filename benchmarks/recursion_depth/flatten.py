def flatten(nested):
    """Flatten an arbitrarily nested list into a single flat list.

    Must handle deeply nested input without hitting RecursionError.
    """
    result = []
    for item in nested:
        if isinstance(item, list):
            result.extend(flatten(item))
        else:
            result.append(item)
    return result
