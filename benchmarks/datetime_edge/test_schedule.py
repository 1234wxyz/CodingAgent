from datetime import date
from schedule import next_weekday

def test_next_monday_from_wednesday():
    # 2026-03-25 is Wednesday (weekday=2), next Monday (0) is 2026-03-30
    result = next_weekday(date(2026, 3, 25), 0)
    assert result == date(2026, 3, 30), f"Got {result}"

def test_next_wednesday_from_wednesday():
    # If today is Wednesday and we ask for next Wednesday, should be +7 not +0
    result = next_weekday(date(2026, 3, 25), 2)
    assert result == date(2026, 4, 1), f"Got {result}, expected 2026-04-01 (not same day)"

def test_next_friday_from_monday():
    result = next_weekday(date(2026, 3, 23), 4)
    assert result == date(2026, 3, 27), f"Got {result}"

if __name__ == "__main__":
    test_next_monday_from_wednesday()
    test_next_wednesday_from_wednesday()
    test_next_friday_from_monday()
    print("All tests passed.")
