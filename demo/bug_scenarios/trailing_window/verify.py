from windowing import trailing_window


def main() -> None:
    assert trailing_window([1, 2, 3, 4, 5], 3) == [3, 4, 5]
    assert trailing_window([1, 2], 5) == [1, 2]
    assert trailing_window([1, 2], 0) == []
    print("verification passed: trailing_window")


if __name__ == "__main__":
    main()
