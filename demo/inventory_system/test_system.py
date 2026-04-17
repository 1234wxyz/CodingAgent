"""Integration tests for the inventory management system."""

from models import Product, OrderStatus
from inventory import InventoryManager
from pricing import apply_pricing, calculate_bulk_discount
from shipping import calculate_shipping, FREE_SHIPPING_THRESHOLD
from service import OrderService, CheckoutError
from reports import SalesReport


def _build_inventory() -> InventoryManager:
    inv = InventoryManager()
    inv.add_product(Product("LAP-001", "Laptop", 999.99, stock=10,
                            category="electronics", weight_kg=2.5))
    inv.add_product(Product("USB-010", "USB Cable", 9.99, stock=200,
                            category="electronics", weight_kg=0.05))
    inv.add_product(Product("TEE-100", "T-Shirt", 19.99, stock=50,
                            category="clothing", weight_kg=0.2))
    inv.add_product(Product("RIC-500", "Rice 5kg", 12.50, stock=80,
                            category="food", weight_kg=5.0))
    return inv


# ---------- Inventory Tests ----------

def test_inventory_basics():
    inv = _build_inventory()
    assert inv.get_product("LAP-001").name == "Laptop"
    assert inv.get_product("NONEXIST") is None
    assert len(inv.list_products()) == 4
    assert len(inv.list_products(category="electronics")) == 2


def test_stock_operations():
    inv = _build_inventory()
    assert inv.reserve_stock("USB-010", 5) is True
    assert inv.get_product("USB-010").stock == 195
    assert inv.reserve_stock("LAP-001", 999) is False  # insufficient
    assert inv.restock("LAP-001", 5) is True
    assert inv.get_product("LAP-001").stock == 15


def test_low_stock_alert():
    inv = _build_inventory()
    inv.reserve_stock("LAP-001", 7)  # stock -> 3
    low = inv.check_low_stock(threshold=5)
    skus = [p.sku for p in low]
    assert "LAP-001" in skus


# ---------- Pricing Tests ----------

def test_bulk_discount_tiers():
    assert calculate_bulk_discount(5) == 0.0
    assert calculate_bulk_discount(10) == 0.05
    assert calculate_bulk_discount(25) == 0.10
    assert calculate_bulk_discount(100) == 0.15


def test_pricing_no_discount():
    inv = _build_inventory()
    svc = OrderService(inv)
    order = svc.create_order("P-001")
    svc.add_to_order(order, "TEE-100", 2)  # 2 * 19.99 = 39.98
    pricing = apply_pricing(order)
    assert pricing["subtotal"] == 39.98
    assert pricing["discount"] == 0.0
    assert pricing["tax"] == round(39.98 * 0.08, 2)  # clothing 8%


def test_pricing_with_order_discount():
    inv = _build_inventory()
    svc = OrderService(inv)
    order = svc.create_order("P-002")
    order.discount_rate = 0.20  # 20% coupon
    svc.add_to_order(order, "LAP-001", 1)  # 999.99
    pricing = apply_pricing(order)
    assert pricing["discount_rate"] == 0.20
    expected_discount = round(999.99 * 0.20, 2)
    assert pricing["discount"] == expected_discount


# ---------- Shipping Tests ----------

def test_free_shipping():
    """Orders >= $200 total should get free shipping."""
    inv = _build_inventory()
    svc = OrderService(inv)
    order = svc.create_order("S-001")
    svc.add_to_order(order, "LAP-001", 1)  # $999.99 -> well above threshold
    pricing = apply_pricing(order)
    shipping = calculate_shipping(order, pricing["total"])
    assert shipping["free_shipping"] is True
    assert shipping["shipping_cost"] == 0.0


def test_paid_shipping_by_weight():
    inv = _build_inventory()
    svc = OrderService(inv)
    order = svc.create_order("S-002")
    svc.add_to_order(order, "USB-010", 1)  # $9.99, 0.05kg
    pricing = apply_pricing(order)
    shipping = calculate_shipping(order, pricing["total"])
    assert shipping["free_shipping"] is False
    assert shipping["shipping_cost"] == 8.0  # lightest tier


# ---------- Checkout Integration Tests ----------

def test_full_checkout():
    inv = _build_inventory()
    svc = OrderService(inv)
    order = svc.create_order("C-001")
    svc.add_to_order(order, "LAP-001", 1)
    svc.add_to_order(order, "USB-010", 3)
    result = svc.checkout(order)
    assert order.status == OrderStatus.CONFIRMED
    assert result["grand_total"] > 0
    assert inv.get_product("LAP-001").stock == 9
    assert inv.get_product("USB-010").stock == 197


def test_checkout_empty_order():
    inv = _build_inventory()
    svc = OrderService(inv)
    order = svc.create_order("C-002")
    try:
        svc.checkout(order)
        assert False, "Should have raised CheckoutError"
    except CheckoutError:
        pass


def test_checkout_insufficient_stock():
    inv = _build_inventory()
    svc = OrderService(inv)
    order = svc.create_order("C-003")
    svc.add_to_order(order, "LAP-001", 5)
    # Drain stock externally
    inv.reserve_stock("LAP-001", 8)
    try:
        svc.checkout(order)
        assert False, "Should have raised CheckoutError"
    except CheckoutError:
        pass


# ---------- Cancellation Test ----------

def test_cancel_restores_stock():
    inv = _build_inventory()
    svc = OrderService(inv)
    order = svc.create_order("X-001")
    svc.add_to_order(order, "TEE-100", 3)
    svc.checkout(order)
    assert inv.get_product("TEE-100").stock == 47
    svc.cancel_order(order)
    assert inv.get_product("TEE-100").stock == 50
    assert order.status == OrderStatus.CANCELLED


# ---------- Report Tests ----------

def test_sales_report():
    inv = _build_inventory()
    svc = OrderService(inv)

    o1 = svc.create_order("R-001")
    svc.add_to_order(o1, "LAP-001", 2)
    svc.add_to_order(o1, "TEE-100", 5)
    svc.checkout(o1)

    o2 = svc.create_order("R-002")
    svc.add_to_order(o2, "RIC-500", 10)
    svc.checkout(o2)

    report = SalesReport(svc.completed_orders)
    assert report.total_orders == 2
    assert report.total_revenue > 0

    by_cat = report.revenue_by_category()
    assert "electronics" in by_cat
    assert "food" in by_cat

    top = report.top_products(n=3)
    assert len(top) <= 3
    assert top[0]["revenue"] >= top[-1]["revenue"]


# ---------- BUG SCENARIO ----------
# This is the test that FAILS due to a bug in the system.
# When a bulk order of heavy items qualifies for a bulk discount,
# the discounted total can drop below $200 and should NOT get
# free shipping. But currently it does, because shipping.py
# receives the pre-discount subtotal instead of the post-discount total.

def test_bulk_discount_affects_shipping():
    """Order with 20% coupon drops total below free-shipping threshold.
    Shipping should NOT be free."""
    inv = _build_inventory()
    svc = OrderService(inv)
    order = svc.create_order("BUG-001")
    order.discount_rate = 0.20  # 20% coupon

    # 11 x T-Shirt @ $19.99 = $219.89 subtotal  (>= $200)
    # 20% discount (coupon > bulk 10%) -> $175.91 discounted
    # + clothing tax 8% -> $189.98 total
    # $189.98 < $200 threshold -> shipping should NOT be free
    # BUG: service.py passes subtotal ($219.89) to shipping instead of
    #       total ($189.98), so shipping incorrectly shows as free.
    svc.add_to_order(order, "TEE-100", 11)

    result = svc.checkout(order)

    # The bug: shipping incorrectly shows as free
    assert result["shipping"]["free_shipping"] is False, (
        f"Expected paid shipping: discounted total ${result['pricing']['total']:.2f} "
        f"is below ${FREE_SHIPPING_THRESHOLD} threshold, "
        f"but shipping used subtotal ${result['pricing']['subtotal']:.2f} and gave free shipping"
    )
    assert result["grand_total"] > result["pricing"]["total"], (
        "Grand total should include shipping cost"
    )


# ---------- Runner ----------

def main():
    tests = [
        test_inventory_basics,
        test_stock_operations,
        test_low_stock_alert,
        test_bulk_discount_tiers,
        test_pricing_no_discount,
        test_pricing_with_order_discount,
        test_free_shipping,
        test_paid_shipping_by_weight,
        test_full_checkout,
        test_checkout_empty_order,
        test_checkout_insufficient_stock,
        test_cancel_restores_stock,
        test_sales_report,
        test_bulk_discount_affects_shipping,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"  PASS  {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")

    print(f"\n{passed} passed, {failed} failed, {len(tests)} total")
    if failed:
        raise SystemExit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
