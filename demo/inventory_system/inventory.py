"""Inventory management — stock tracking and replenishment."""

from typing import Dict, List, Optional
from models import Product


class InventoryManager:
    """Central inventory registry."""

    def __init__(self):
        self._products: Dict[str, Product] = {}

    def add_product(self, product: Product) -> None:
        self._products[product.sku] = product

    def get_product(self, sku: str) -> Optional[Product]:
        return self._products.get(sku)

    def list_products(self, category: Optional[str] = None) -> List[Product]:
        products = list(self._products.values())
        if category:
            products = [p for p in products if p.category == category]
        return products

    def restock(self, sku: str, quantity: int) -> bool:
        product = self.get_product(sku)
        if product is None:
            return False
        product.stock += quantity
        return True

    def reserve_stock(self, sku: str, quantity: int) -> bool:
        """Deduct stock for an order. Returns False if insufficient."""
        product = self.get_product(sku)
        if product is None or product.stock < quantity:
            return False
        product.stock -= quantity
        return True

    def check_low_stock(self, threshold: int = 5) -> List[Product]:
        return [p for p in self._products.values() if p.stock <= threshold]
