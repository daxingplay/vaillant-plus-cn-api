"""Define tests for models."""

import pytest
from vaillant_plus_cn_api.model import Token

TEST_RESULT = "eyJhcHBfaWQiOiAiMSIsICJ1c2VybmFtZSI6ICJ1MSIsICJwYXNzd29yZCI6ICJwYXNzMSIsICJ0b2tlbiI6ICJ0azEiLCAidWlkIjogInVpZDEifQ=="

def test_model_token_serialize() -> None:
    """Test serialize token model.
    """
    token = Token(
      app_id="1",
      username="u1",
      password="pass1",
      token="tk1",
      uid="uid1"
    )
    s = token.serialize()
    assert s == TEST_RESULT

def test_model_token_deserialize() -> None:
    """Test deserialize token model.
    """
    token = Token.deserialize(TEST_RESULT)
    assert token.app_id == "1"
    assert token.username == "u1"
    assert token.password == "pass1"
    assert token.token == "tk1"
    assert token.uid == "uid1"