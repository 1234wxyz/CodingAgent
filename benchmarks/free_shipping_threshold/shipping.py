FREE_SHIPPING_THRESHOLD = 50.0
STANDARD_SHIPPING_FEE = 7.99
MEMBER_SHIPPING_DISCOUNT = 2.0


def shipping_cost(subtotal, is_member=False):
    if subtotal > FREE_SHIPPING_THRESHOLD:
        return 0.0

    cost = STANDARD_SHIPPING_FEE
    if is_member:
        cost -= MEMBER_SHIPPING_DISCOUNT
    return round(max(cost, 0.0), 2)
