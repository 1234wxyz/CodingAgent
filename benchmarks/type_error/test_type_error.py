from formatter import format_user_greeting


def main() -> None:
    assert format_user_greeting("Alice", 30) == "Hello, Alice! You are 30 years old."
    assert format_user_greeting("Bob", 0) == "Hello, Bob! You are 0 years old."
    assert format_user_greeting("Eve", "25") == "Hello, Eve! You are 25 years old."
    print("PASS")


if __name__ == "__main__":
    main()
