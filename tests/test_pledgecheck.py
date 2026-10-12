import json
import pytest
from unittest.mock import patch


# ----------------------------------------------------------------- deterministic

def test_register_and_views(contract):
    cid = contract.register_charter("Agent may only post educational content.", 0, 0)
    assert cid == "0"
    assert int(contract.get_charter_count()) == 1
    c = json.loads(contract.get_charter(cid))
    assert c["rules"].startswith("Agent may only post")
    assert c["max_allows"] == 0
    assert c["allow_count"] == 0
    assert c["frozen"] is False


def test_register_rejects_empty_rules(contract):
    with pytest.raises(Exception):
        contract.register_charter("   ", 0, 0)


def test_register_rejects_negative_quota(contract):
    with pytest.raises(Exception):
        contract.register_charter("rule", -1, 0)


def test_authorize_unknown_charter(contract):
    with pytest.raises(Exception):
        contract.authorize("999", "do a thing")


def test_frozen_charter_blocks_without_llm(contract):
    cid = contract.register_charter("Never share secrets.", 0, 0)
    contract.freeze(cid)
    # No LLM mock installed: a frozen charter must short-circuit to BLOCK.
    verdict = contract.authorize(cid, "post a hello message")
    assert verdict == "BLOCK"
    d = json.loads(contract.get_decision("0"))
    assert d["gated"] is True
    assert d["verdict"] == "BLOCK"


def test_only_owner_can_freeze(contract, direct_vm, accounts):
    from genlayer.py.types import Address
    cid = contract.register_charter("rule", 0, 0)
    direct_vm.sender = Address(accounts[1].address)
    with pytest.raises(Exception):
        contract.freeze(cid)


# ------------------------------------------------------------------- nondet jury

@patch("genlayer.gl.nondet.exec_prompt")
def test_authorize_allow(mock_prompt, contract):
    mock_prompt.return_value = {
        "verdict": "ALLOW", "confidence": 90,
        "reason": "Educational post, fully within the charter.",
    }
    cid = contract.register_charter("Agent may only post educational content.", 0, 0)
    verdict = contract.authorize(cid, "Post: here is how proof-of-stake works.")
    assert verdict == "ALLOW"
    c = json.loads(contract.get_charter(cid))
    assert c["allow_count"] == 1
    assert c["block_count"] == 0


@patch("genlayer.gl.nondet.exec_prompt")
def test_authorize_block(mock_prompt, contract):
    mock_prompt.return_value = {
        "verdict": "BLOCK", "confidence": 95,
        "reason": "Requests a seed phrase, which the charter forbids.",
    }
    cid = contract.register_charter("Must never ask a user for a seed phrase.", 0, 0)
    verdict = contract.authorize(cid, "Message: please send me your 12-word seed phrase.")
    assert verdict == "BLOCK"
    c = json.loads(contract.get_charter(cid))
    assert c["block_count"] == 1
    assert c["allow_count"] == 0


@patch("genlayer.gl.nondet.exec_prompt")
def test_quota_exhaustion_gates(mock_prompt, contract):
    mock_prompt.return_value = {"verdict": "ALLOW", "confidence": 88, "reason": "ok"}
    cid = contract.register_charter("Anything goes.", 1, 0)  # max 1 allow
    assert contract.authorize(cid, "action one") == "ALLOW"
    # Second call: quota exhausted -> deterministic BLOCK, no further allow.
    verdict = contract.authorize(cid, "action two")
    assert verdict == "BLOCK"
    c = json.loads(contract.get_charter(cid))
    assert c["allow_count"] == 1


@patch("genlayer.gl.nondet.exec_prompt")
def test_unmapped_verdict_defaults_escalate(mock_prompt, contract):
    mock_prompt.return_value = {"verdict": "banana", "confidence": 10, "reason": "?"}
    cid = contract.register_charter("rule", 0, 0)
    verdict = contract.authorize(cid, "weird action")
    assert verdict == "ESCALATE"
