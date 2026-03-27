from pricing import discount_rate


def total_after_discount(subtotal, customer_tier):
    rate = discount_rate(customer_tier)
    return round(subtotal * (1 - rate), 2)
