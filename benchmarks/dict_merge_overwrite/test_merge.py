from utils import dict_merge

def test_merge_does_not_mutate_base():
    base = {"a": 1, "b": 2}
    original_base = dict(base)
    override = {"b": 3, "c": 4}
    result = dict_merge(base, override)
    assert result == {"a": 1, "b": 3, "c": 4}, f"Wrong result: {result}"
    assert base == original_base, f"base was mutated: {base} != {original_base}"

def test_merge_empty():
    assert dict_merge({}, {"x": 1}) == {"x": 1}
    base = {"x": 1}
    original = dict(base)
    dict_merge(base, {})
    assert base == original

if __name__ == "__main__":
    test_merge_does_not_mutate_base()
    test_merge_empty()
    print("All tests passed.")
