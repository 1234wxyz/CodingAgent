import sys
from flatten import flatten

def test_simple():
    assert flatten([1, [2, 3], [4, [5]]]) == [1, 2, 3, 4, 5]

def test_empty():
    assert flatten([]) == []
    assert flatten([[], [[]]]) == []

def test_deep_nesting():
    # Build a list nested 2000 levels deep — recursive approach will fail
    deep = [42]
    for _ in range(2000):
        deep = [deep]
    try:
        result = flatten(deep)
    except RecursionError:
        raise AssertionError("RecursionError: flatten must use iterative approach for deep nesting")
    assert result == [42], f"Got {result}"

if __name__ == "__main__":
    test_simple()
    test_empty()
    test_deep_nesting()
    print("All tests passed.")
