"""Pricing engine — discounts, tax, and final price calculation."""

from models import Order

# Tax rates by category
TAX_RATES = {
    "electronics": 0.15,
    "food": 0.05,
    "clothing": 0.08,
    "general": 0.10,
}

# Bulk discount tiers: (min_quantity, discount_rate)
BULK_TIERS = [
    (50, 0.15),
    (20, 0.10),
    (10, 0.05),
]


def get_tax_rate(category: str) -> float:
    return TAX_RATES.get(category, TAX_RATES["general"])


def calculate_bulk_discount(total_quantity: int) -> float:
    """Return discount rate based on total item count."""
    for min_qty, rate in BULK_TIERS:
        if total_quantity >= min_qty:
            return rate
    return 0.0


def apply_pricing(order: Order) -> dict:
    """Compute full pricing breakdown for an order.

    Returns dict with: subtotal, discount, tax, total
    """
    subtotal = order.subtotal
    total_quantity = sum(item.quantity for item in order.items)

    # Apply bulk discount OR order-level discount, whichever is larger
    bulk_rate = calculate_bulk_discount(total_quantity)
    effective_rate = max(bulk_rate, order.discount_rate)
    discount = round(subtotal * effective_rate, 2)

    discounted = subtotal - discount

    # Calculate tax per item category (weighted)
    tax = 0.0
    for item in order.items:
        item_share = item.line_total / subtotal if subtotal > 0 else 0
        category_rate = get_tax_rate(item.product.category)
        tax += discounted * item_share * category_rate
    tax = round(tax, 2)

    total = round(discounted + tax, 2)

    return {
        "subtotal": subtotal,
        "discount": discount,
        "discount_rate": effective_rate,
        "tax": tax,
        "total": total,
    }
