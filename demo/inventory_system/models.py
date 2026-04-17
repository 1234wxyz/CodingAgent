"""Domain models for the inventory management system."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


@dataclass
class Product:
    sku: str
    name: str
    price: float
    stock: int = 0
    category: str = "general"
    weight_kg: float = 0.0

    def is_available(self, quantity: int = 1) -> bool:
        return self.stock >= quantity


@dataclass
class OrderItem:
    product: Product
    quantity: int

    @property
    def line_total(self) -> float:
        return self.product.price * self.quantity

    @property
    def line_weight(self) -> float:
        return self.product.weight_kg * self.quantity


@dataclass
class Order:
    order_id: str
    items: List[OrderItem] = field(default_factory=list)
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    discount_rate: float = 0.0
    shipping_address: str = ""

    def add_item(self, product: Product, quantity: int) -> None:
        for item in self.items:
            if item.product.sku == product.sku:
                item.quantity += quantity
                return
        self.items.append(OrderItem(product=product, quantity=quantity))

    @property
    def subtotal(self) -> float:
        return sum(item.line_total for item in self.items)

    @property
    def total_weight(self) -> float:
        return sum(item.line_weight for item in self.items)
