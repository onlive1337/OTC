from data.connection import DatabaseMixin
from data.user_repo import UserRepoMixin
from data.chat_repo import ChatRepoMixin


class UserData(DatabaseMixin, UserRepoMixin, ChatRepoMixin):
    pass