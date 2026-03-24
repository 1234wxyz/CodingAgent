def classify_temperature(temp):
    """Classify temperature into categories."""
    if temp < 0:
        return "freezing"
    elif temp < 15:
        return "cold"
    elif temp < 25:
        return "comfortable"
    elif temp < 35:
        # Missing return statement
        "hot"
    else:
        return "extreme"
