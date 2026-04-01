from services import get_user_label


class User:
    def __init__(self, name, role="member"):
        self.name = name
        self.role = role

    def label(self):
        return get_user_label(self)
