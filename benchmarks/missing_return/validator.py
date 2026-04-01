def classify_temperature(temp):
    """Classify temperature into categories."""
    if temp < 0:
        return "freezing"
    if temp < 15:
        return "cold"
    if temp < 25:
        return "comfortable"
    if temp < 35:
        "hot"
    return "extreme"
