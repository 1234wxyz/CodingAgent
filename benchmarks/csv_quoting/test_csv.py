from csvutil import csv_row_to_string

def test_simple_fields():
    assert csv_row_to_string(["a", "b", "c"]) == "a,b,c"

def test_field_with_comma():
    result = csv_row_to_string(["hello", "world, earth", "ok"])
    assert result == 'hello,"world, earth",ok', f"Got: {result}"

def test_field_with_quote():
    result = csv_row_to_string(['say "hi"', "b"])
    assert result == '"say ""hi""",b', f"Got: {result}"

def test_empty_fields():
    assert csv_row_to_string(["", "", ""]) == ",,"

if __name__ == "__main__":
    test_simple_fields()
    test_field_with_comma()
    test_field_with_quote()
    test_empty_fields()
    print("All tests passed.")
