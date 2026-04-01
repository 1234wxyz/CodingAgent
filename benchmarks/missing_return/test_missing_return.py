from validator import classify_temperature


def main() -> None:
    assert classify_temperature(-5) == "freezing"
    assert classify_temperature(10) == "cold"
    assert classify_temperature(20) == "comfortable"
    assert classify_temperature(30) == "hot"
    assert classify_temperature(40) == "extreme"
    print("PASS")


if __name__ == "__main__":
    main()
