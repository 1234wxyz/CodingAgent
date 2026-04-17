"""Shipping cost calculator."""

from models import Order

# Shipping rate tiers by weight (kg)
WEIGHT_RATES = [
    (30, 25.0),   # 30kg+  -> $25 flat
    (10, 15.0),   # 10-29kg -> $15 flat
    (0, 8.0),     # 0-9kg  -> $8 flat
]

FREE_SHIPPING_THRESHOLD = 200.0  # free shipping if order total >= $200


def calculate_shipping(order: Order, order_total: float) -> dict:
    """Calculate shipping cost.

    Free shipping for orders totalling >= $200 (after discount + tax).
    Otherwise, cost is based on total package weight.

    Returns dict with: weight_kg, shipping_cost, free_shipping
    """
    weight = order.total_weight

    if order_total >= FREE_SHIPPING_THRESHOLD:
        return {
            "weight_kg": round(weight, 2),
            "shipping_cost": 0.0,
            "free_shipping": True,
        }

    cost = _weight_based_cost(weight)

    return {
        "weight_kg": round(weight, 2),
        "shipping_cost": cost,
        "free_shipping": False,
    }


def _weight_based_cost(weight_kg: float) -> float:
    for min_weight, rate in WEIGHT_RATES:
        if weight_kg >= min_weight:
            return rate
    return WEIGHT_RATES[-1][1]
