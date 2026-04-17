"""Order processing service — orchestrates the full checkout flow."""

from typing import Optional
from models import Order, OrderStatus, Product
from inventory import InventoryManager
from pricing import apply_pricing
from shipping import calculate_shipping


class CheckoutError(Exception):
    pass


class OrderService:
    """Handles order creation, checkout, and cancellation."""

    def __init__(self, inventory: InventoryManager):
        self.inventory = inventory
        self.completed_orders = []

    def create_order(self, order_id: str) -> Order:
        return Order(order_id=order_id)

    def add_to_order(self, order: Order, sku: str, quantity: int) -> None:
        product = self.inventory.get_product(sku)
        if product is None:
            raise CheckoutError(f"Product {sku} not found")
        if not product.is_available(quantity):
            raise CheckoutError(
                f"Insufficient stock for {sku}: "
                f"requested {quantity}, available {product.stock}"
            )
        order.add_item(product, quantity)

    def checkout(self, order: Order) -> dict:
        """Process a full checkout: reserve stock, compute pricing & shipping.

        Returns a summary dict with pricing, shipping, and grand_total.
        """
        if not order.items:
            raise CheckoutError("Cannot checkout an empty order")

        # Reserve stock for each item
        for item in order.items:
            ok = self.inventory.reserve_stock(item.product.sku, item.quantity)
            if not ok:
                raise CheckoutError(
                    f"Failed to reserve stock for {item.product.sku}"
                )

        # Compute pricing
        pricing = apply_pricing(order)

        # Compute shipping
        shipping = calculate_shipping(order, pricing["subtotal"])

        grand_total = round(pricing["total"] + shipping["shipping_cost"], 2)

        order.status = OrderStatus.CONFIRMED
        self.completed_orders.append(order)

        return {
            "order_id": order.order_id,
            "pricing": pricing,
            "shipping": shipping,
            "grand_total": grand_total,
        }

    def cancel_order(self, order: Order) -> None:
        """Cancel an order and restore stock."""
        if order.status != OrderStatus.CONFIRMED:
            raise CheckoutError("Only confirmed orders can be cancelled")
        for item in order.items:
            self.inventory.restock(item.product.sku, item.quantity)
        order.status = OrderStatus.CANCELLED
