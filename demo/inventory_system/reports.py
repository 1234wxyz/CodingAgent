"""Sales reporting and analytics."""

from typing import Dict, List
from models import Order, OrderStatus


class SalesReport:
    """Aggregates completed orders into sales statistics."""

    def __init__(self, orders: List[Order]):
        self._orders = [o for o in orders if o.status == OrderStatus.CONFIRMED]

    @property
    def total_orders(self) -> int:
        return len(self._orders)

    @property
    def total_revenue(self) -> float:
        return round(sum(o.subtotal for o in self._orders), 2)

    def revenue_by_category(self) -> Dict[str, float]:
        breakdown: Dict[str, float] = {}
        for order in self._orders:
            for item in order.items:
                cat = item.product.category
                breakdown[cat] = breakdown.get(cat, 0) + item.line_total
        return {k: round(v, 2) for k, v in breakdown.items()}

    def top_products(self, n: int = 5) -> List[dict]:
        counts: Dict[str, dict] = {}
        for order in self._orders:
            for item in order.items:
                sku = item.product.sku
                if sku not in counts:
                    counts[sku] = {
                        "sku": sku,
                        "name": item.product.name,
                        "units_sold": 0,
                        "revenue": 0.0,
                    }
                counts[sku]["units_sold"] += item.quantity
                counts[sku]["revenue"] += item.line_total
        ranked = sorted(counts.values(), key=lambda x: x["revenue"], reverse=True)
        return ranked[:n]
