from search import search_pattern

def test_simple_search():
    text = "hello world\nfoo bar\nhello again"
    assert search_pattern(text, "hello") == [1, 3]

def test_pattern_with_dot():
    text = "version 1.2.3\nversion 1x2x3\nother"
    # Should match only the literal "1.2.3", not "1x2x3"
    result = search_pattern(text, "1.2.3")
    assert result == [1], f"Got {result}, dot should be literal not wildcard"

def test_pattern_with_star():
    text = "file*.txt\nfile_a.txt\nother"
    result = search_pattern(text, "file*.txt")
    assert result == [1], f"Got {result}, star should be literal"

def test_pattern_with_parens():
    text = "call foo(bar)\nno match\ncall foo(bar) again"
    result = search_pattern(text, "foo(bar)")
    assert result == [1, 3], f"Got {result}"

if __name__ == "__main__":
    test_simple_search()
    test_pattern_with_dot()
    test_pattern_with_star()
    test_pattern_with_parens()
    print("All tests passed.")
