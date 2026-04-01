from checkout import final_total
from shipping import shipping_cost


def main() -> None:
    assert shipping_cost(50.0) == 0.0
    assert shipping_cost(49.99) == 7.99
    assert shipping_cost(20.0, is_member=True) == 5.99
    assert final_total(50.0) == 50.0
    assert final_total(20.0, is_member=True) == 25.99
    print("PASS")


if __name__ == "__main__":
    main()
