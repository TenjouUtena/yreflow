"""Tests for Realm dataclass."""

import dataclasses

import pytest

from yreflow.protocol.realm import Realm


class TestRealmFromKey:
    def test_wolfery_realm(self):
        r = Realm.from_key("wolfery")
        assert r.key == "wolfery"
        assert r.ws_url == "wss://api.wolfery.com/"
        assert r.file_url == "https://file.wolfery.com"
        assert r.cookie_name == "wolfery-auth-token"

    def test_custom_realm(self):
        r = Realm.from_key("aurellion")
        assert r.key == "aurellion"
        assert r.ws_url == "wss://api.aurellion.mucklet.com/"
        assert r.file_url == "https://file.aurellion.mucklet.com"
        assert r.cookie_name == "aurellion-auth-token"

    def test_another_custom_realm(self):
        r = Realm.from_key("lastflameinn")
        assert r.ws_url == "wss://api.lastflameinn.mucklet.com/"

    def test_realm_frozen(self):
        r = Realm.from_key("wolfery")
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.key = "other"
