from shipping import shipping_cost


def final_total(subtotal, is_member=False):
    shipping = shipping_cost(subtotal, is_member=is_member)
    return round(subtotal + shipping, 2)
