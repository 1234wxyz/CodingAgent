def dict_merge(base, override):
    """Merge override into base and return the result.

    Should NOT modify the original base dict.
    """
    base.update(override)
    return base
