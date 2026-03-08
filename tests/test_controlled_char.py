"""Tests for ControlledChar dataclass properties."""

from yreflow.protocol.controlled_char import ControlledChar


class TestRegularChar:
    def test_ctrl_id(self):
        cc = ControlledChar("alice")
        assert cc.ctrl_id == "alice"

    def test_is_puppet_false(self):
        cc = ControlledChar("alice")
        assert cc.is_puppet is False

    def test_char_path(self):
        cc = ControlledChar("alice")
        assert cc.char_path == "core.char.alice"

    def test_ctrl_path(self):
        cc = ControlledChar("alice")
        assert cc.ctrl_path == "core.char.alice.ctrl"

    def test_str(self):
        cc = ControlledChar("alice")
        assert str(cc) == "alice"


class TestPuppetChar:
    def test_ctrl_id(self):
        cc = ControlledChar("puppet1", puppeteer_id="owner1")
        assert cc.ctrl_id == "puppet1_owner1"

    def test_is_puppet_true(self):
        cc = ControlledChar("puppet1", puppeteer_id="owner1")
        assert cc.is_puppet is True

    def test_char_path(self):
        cc = ControlledChar("puppet1", puppeteer_id="owner1")
        assert cc.char_path == "core.char.owner1.puppet.puppet1"

    def test_ctrl_path(self):
        cc = ControlledChar("puppet1", puppeteer_id="owner1")
        assert cc.ctrl_path == "core.char.owner1.puppet.puppet1.ctrl"


class TestEquality:
    def test_equal_controlled_chars(self):
        a = ControlledChar("alice")
        b = ControlledChar("alice")
        assert a == b

    def test_equal_to_string(self):
        cc = ControlledChar("alice")
        assert cc == "alice"

    def test_puppet_equal_to_string(self):
        cc = ControlledChar("p1", puppeteer_id="o1")
        assert cc == "p1_o1"

    def test_hash_consistent(self):
        a = ControlledChar("alice")
        b = ControlledChar("alice")
        assert hash(a) == hash(b)

    def test_hash_in_set(self):
        s = {ControlledChar("alice"), ControlledChar("alice")}
        assert len(s) == 1
