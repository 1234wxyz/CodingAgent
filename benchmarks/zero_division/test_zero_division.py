from calculator import average


def main() -> None:
    assert average([1, 2, 3]) == 2.0
    assert average([]) == 0.0
    print("PASS")


if __name__ == "__main__":
    main()
