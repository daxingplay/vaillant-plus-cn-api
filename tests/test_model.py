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
      access_token="tk1",
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
    assert token.access_token == "tk1"
    assert token.uid == "uid1"

def test_model_token_equals() -> None:
    """Test equals method.
    """
    token1 = Token.deserialize(TEST_RESULT)
    token2 = Token.deserialize(TEST_RESULT)
    assert Token.equals(token1, token2)

    # change the order of some props, but value is the same
    token3 = Token.deserialize("eyJhcHBfaWQiOiAiMSIsICJ1aWQiOiAidWlkMSIsICJ1c2VybmFtZSI6ICJ1MSIsICJwYXNzd29yZCI6ICJwYXNzMSIsICJ0b2tlbiI6ICJ0azEifQ==")
    assert Token.equals(token1, token3)

    # change app_id
    token4 = Token.deserialize("eyJhcHBfaWQiOiAiMiIsICJ1aWQiOiAidWlkMSIsICJ1c2VybmFtZSI6ICJ1MSIsICJwYXNzd29yZCI6ICJwYXNzMSIsICJ0b2tlbiI6ICJ0azEifQ==")
    assert Token.equals(token1, token4) is False

    # change uid
    token5 = Token.deserialize("eyJhcHBfaWQiOiAiMSIsICJ1aWQiOiAidWlkMiIsICJ1c2VybmFtZSI6ICJ1MSIsICJwYXNzd29yZCI6ICJwYXNzMSIsICJ0b2tlbiI6ICJ0azEifQ==")
    assert Token.equals(token1, token5) is False