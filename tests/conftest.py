import pytest

from support import flask_app, login, make_user


@pytest.fixture
def guest():
    return flask_app.test_client()


@pytest.fixture
def user():
    uid = make_user()
    return login(flask_app.test_client(), uid), uid
