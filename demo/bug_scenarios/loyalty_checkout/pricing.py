DISCOUNT_BY_TIER = {
    "standard": 0.0,
    "pro": 0.05,
    "enterprise": 0.15,
}


def discount_rate(customer_tier):
    return DISCOUNT_BY_TIER.get(customer_tier, 0.15)
