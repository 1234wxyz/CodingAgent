"""Verify that the circular import is resolved."""
from models import User
from services import create_default_user

u = User("Alice", "admin")
assert u.label() == "[admin] Alice"

guest = create_default_user()
assert guest.label() == "[visitor] Guest"
print("PASS")
