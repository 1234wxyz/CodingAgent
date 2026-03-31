def csv_row_to_string(fields):
    """Convert a list of fields into a single CSV line.

    Fields containing commas or quotes should be properly quoted.
    """
    return ",".join(str(f) for f in fields)
