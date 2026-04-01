from models import User


def get_user_label(user):
    return f"[{user.role}] {user.name}"


def create_default_user():
    return User("Guest", "visitor")
