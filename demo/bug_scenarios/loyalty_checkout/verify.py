from checkout import total_after_discount


def main() -> None:
    assert total_after_discount(200, "pro") == 190.0
    assert total_after_discount(200, "enterprise") == 170.0
    assert total_after_discount(200, "unknown") == 200.0
    print("verification passed: loyalty_checkout")


if __name__ == "__main__":
    main()
