from paths import join_path


def main() -> None:
    assert join_path("/api", "users") == "/api/users"
    assert join_path("/api/", "users") == "/api/users"
    assert join_path("/api", "/users") == "/api/users"
    assert join_path("/", "health") == "/health"
    assert join_path("", "health") == "health"
    print("PASS")


if __name__ == "__main__":
    main()
