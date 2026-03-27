def trailing_window(items, size):
    if size <= 0:
        return []
    return items[-(size + 1):]
