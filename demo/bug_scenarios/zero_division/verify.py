from calculator import average


def main() -> None:
    assert average([1, 2, 3]) == 2.0
    assert average([]) == 0.0
    print("verification passed: zero_division")


if __name__ == "__main__":
    main()
