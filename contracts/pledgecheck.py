# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *

import json
import typing
import datetime
from dataclasses import dataclass

# PledgeCheck - a reusable GenLayer authorization-gate primitive.
#
# An owner registers a "charter": a few plain-language rules that an AI agent
# must honour (e.g. "may only post educational content" and "must never ask a
# user for a password or seed phrase"). BEFORE the agent performs an action it
# calls authorize(charter_id, action_text). A decentralized LLM jury rules
# whether that concrete action is permitted under the SPIRIT of the charter and
# returns ALLOW / BLOCK / ESCALATE together with a confidence and a short reason.
#
# Consensus is reached on the MEANING of the ruling: a validator re-runs its own
# independent judgement and agrees only if it lands on the SAME verdict and a
# comparable confidence band - never on JSON shape. The charter also carries a
# hard allow-quota, a time-to-live and an owner freeze switch, which are checked
# deterministically (no LLM spend) so the primitive doubles as a rate- and
# lifetime-bounded capability gate in front of autonomous agent actions.
#
# Reusable guardrail: plug it in front of an agent's "send", "post", "spend" or
# "call tool" step. It is not a one-off demo - the rules, quota and TTL are all
# parameters, so the same contract gates many different agents and policies.


def _now() -> int:
    # genvm makes plain datetime deterministic across validators for a given tx.
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp())


def _norm_verdict(raw: typing.Any) -> str:
    v = str(raw or "").strip().upper()
    if "BLOCK" in v or "DENY" in v or "REJECT" in v or "FORBID" in v:
        return "BLOCK"
    if "ESCAL" in v or "REVIEW" in v or "UNCLEAR" in v or "UNSURE" in v:
        return "ESCALATE"
    if "ALLOW" in v or "PERMIT" in v or "APPROV" in v or v == "OK":
        return "ALLOW"
    # Fail safe: anything we cannot map does not get a free ALLOW.
    return "ESCALATE"


def _clamp_conf(raw: typing.Any) -> int:
    try:
        c = int(raw)
    except Exception:
        c = 0
    return max(0, min(100, c))


def _band(raw: typing.Any) -> int:
    c = _clamp_conf(raw)
    return 0 if c < 40 else (1 if c < 80 else 2)


@allow_storage
@dataclass
class Charter:
    owner: str
    rules: str
    max_allows: bigint       # 0 means unlimited
    allow_count: bigint
    block_count: bigint
    expires_at: bigint       # epoch seconds; 0 means never expires
    frozen: bool


@allow_storage
@dataclass
class Decision:
    charter_id: str
    action: str
    verdict: str             # ALLOW | BLOCK | ESCALATE
    confidence: bigint       # 0..100
    reason: str
    gated: bool              # True if decided deterministically (quota/ttl/freeze)
    at: bigint


class Contract(gl.Contract):
    charters: TreeMap[str, Charter]
    decisions: TreeMap[str, Decision]
    next_charter_id: bigint
    next_decision_id: bigint

    def __init__(self):
        self.next_charter_id = bigint(0)
        self.next_decision_id = bigint(0)

    # ------------------------------------------------------------------ writes

    @gl.public.write
    def register_charter(self, rules: str, max_allows: int, ttl_secs: int) -> str:
        if not rules or not rules.strip():
            raise gl.vm.UserError("rules must not be empty")
        if len(rules) > 4000:
            raise gl.vm.UserError("rules too long (max 4000 chars)")
        if max_allows < 0:
            raise gl.vm.UserError("max_allows must be >= 0")
        if ttl_secs < 0:
            raise gl.vm.UserError("ttl_secs must be >= 0")

        expires = bigint(0) if ttl_secs == 0 else bigint(_now() + int(ttl_secs))
        cid = str(self.next_charter_id)
        self.charters[cid] = Charter(
            owner=_addr_str(gl.message.sender_address),
            rules=rules.strip(),
            max_allows=bigint(int(max_allows)),
            allow_count=bigint(0),
            block_count=bigint(0),
            expires_at=expires,
            frozen=False,
        )
        self.next_charter_id = self.next_charter_id + bigint(1)
        return cid

    @gl.public.write
    def authorize(self, charter_id: str, action: str) -> str:
        if charter_id not in self.charters:
            raise gl.vm.UserError("charter not found")
        if not action or not action.strip():
            raise gl.vm.UserError("action must not be empty")
        if len(action) > 6000:
            raise gl.vm.UserError("action too long (max 6000 chars)")

        c = self.charters[charter_id]
        act = action.strip()

        # Deterministic gates first - no LLM spend if the charter already forbids.
        if c.frozen:
            return self._record(charter_id, act, "BLOCK", 100,
                                 "charter is frozen by owner", True)
        if int(c.expires_at) != 0 and _now() > int(c.expires_at):
            return self._record(charter_id, act, "BLOCK", 100,
                                 "charter has expired", True)
        if int(c.max_allows) != 0 and int(c.allow_count) >= int(c.max_allows):
            return self._record(charter_id, act, "BLOCK", 100,
                                 "allow quota exhausted", True)

        rules = c.rules

        def leader_fn():
            prompt = f"""You are an impartial authorization gate on a decentralized network.
An autonomous AI agent wants to perform the ACTION below. Decide whether it is
permitted under the SPIRIT of the CHARTER rules. Judge intent and nuance, not
just keywords. If any rule is clearly breached, BLOCK. If it clearly complies,
ALLOW. If it is genuinely ambiguous or needs a human, ESCALATE.

CHARTER RULES:
{rules}

PROPOSED ACTION:
---
{act}
---

Respond ONLY as JSON, no markdown:
{{"verdict":"ALLOW"|"BLOCK"|"ESCALATE","confidence":<integer 0-100>,"reason":"<one or two sentences>"}}"""
            res = gl.nondet.exec_prompt(prompt, response_format="json")
            verdict = _norm_verdict(res.get("verdict"))
            conf = _clamp_conf(res.get("confidence"))
            reason = str(res.get("reason", "")).strip()[:400]
            return json.dumps({"verdict": verdict, "confidence": conf, "reason": reason},
                              sort_keys=True)

        def validator_fn(leader_res: typing.Any) -> bool:
            if not isinstance(leader_res, gl.vm.Return):
                return False
            try:
                leader = json.loads(leader_res.calldata)
            except Exception:
                return False
            mine = json.loads(leader_fn())
            if _norm_verdict(leader.get("verdict")) != _norm_verdict(mine.get("verdict")):
                return False
            return _band(leader.get("confidence")) == _band(mine.get("confidence"))

        raw = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        p = json.loads(raw)
        verdict = _norm_verdict(p.get("verdict"))
        conf = _clamp_conf(p.get("confidence"))
        reason = str(p.get("reason", "")).strip()[:400] or "No rationale."

        if verdict == "ALLOW":
            c.allow_count = c.allow_count + bigint(1)
        elif verdict == "BLOCK":
            c.block_count = c.block_count + bigint(1)

        return self._record(charter_id, act, verdict, conf, reason, False)

    @gl.public.write
    def freeze(self, charter_id: str) -> None:
        c = self._owned(charter_id)
        c.frozen = True

    @gl.public.write
    def unfreeze(self, charter_id: str) -> None:
        c = self._owned(charter_id)
        c.frozen = False

    # ------------------------------------------------------------------ helpers

    def _owned(self, charter_id: str) -> Charter:
        if charter_id not in self.charters:
            raise gl.vm.UserError("charter not found")
        c = self.charters[charter_id]
        if c.owner != _addr_str(gl.message.sender_address):
            raise gl.vm.UserError("only the charter owner may do this")
        return c

    def _record(self, charter_id: str, action: str, verdict: str,
                conf: int, reason: str, gated: bool) -> str:
        did = str(self.next_decision_id)
        self.decisions[did] = Decision(
            charter_id=charter_id,
            action=action[:6000],
            verdict=verdict,
            confidence=bigint(_clamp_conf(conf)),
            reason=reason[:400],
            gated=gated,
            at=bigint(_now()),
        )
        self.next_decision_id = self.next_decision_id + bigint(1)
        return verdict

    # ------------------------------------------------------------------- views

    @gl.public.view
    def get_charter(self, charter_id: str) -> str:
        if charter_id not in self.charters:
            raise gl.vm.UserError("charter not found")
        c = self.charters[charter_id]
        return json.dumps({
            "id": charter_id, "owner": c.owner, "rules": c.rules,
            "max_allows": int(c.max_allows), "allow_count": int(c.allow_count),
            "block_count": int(c.block_count), "expires_at": int(c.expires_at),
            "frozen": bool(c.frozen),
        })

    @gl.public.view
    def get_decision(self, decision_id: str) -> str:
        if decision_id not in self.decisions:
            raise gl.vm.UserError("decision not found")
        d = self.decisions[decision_id]
        return json.dumps({
            "id": decision_id, "charter_id": d.charter_id, "action": d.action,
            "verdict": d.verdict, "confidence": int(d.confidence),
            "reason": d.reason, "gated": bool(d.gated), "at": int(d.at),
        })

    @gl.public.view
    def get_charter_count(self) -> int:
        return int(self.next_charter_id)

    @gl.public.view
    def get_decision_count(self) -> int:
        return int(self.next_decision_id)


def _addr_str(a: typing.Any) -> str:
    try:
        return a.as_hex
    except Exception:
        return str(a)
