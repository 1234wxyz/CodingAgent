from models import User
from services import create_default_user


def main() -> None:
    user = User("Alice", "admin")
    assert user.label() == "[admin] Alice"

    guest = create_default_user()
    assert guest.label() == "[visitor] Guest"
    print("PASS")


if __name__ == "__main__":
    main()
