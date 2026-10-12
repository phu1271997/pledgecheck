# PledgeCheck

**A reusable GenLayer Intelligent Contract: a consensus-graded authorization gate for AI agents.**

PledgeCheck lets an owner write a short, plain-language **charter** — the rules an
autonomous agent must honour — and then checks every action the agent proposes
*before* it runs. A decentralized LLM jury decides whether the action is permitted
under the **spirit** of the charter and returns `ALLOW` / `BLOCK` / `ESCALATE`.
Because GenLayer validators each re-run that judgement and must agree on its
**meaning**, the verdict is trustless: no single node (and no prompt-injected agent)
can wave an action through on its own.

On top of the semantic ruling, each charter carries a hard **allow-quota**, a
**time-to-live**, and an owner **freeze** switch, all enforced deterministically
(no LLM spend). So PledgeCheck is both a *meaning-aware* guardrail and a
*rate- and lifetime-bounded* capability gate in one primitive.

- **Network:** GenLayer studionet (chain id `61999`)
- **Deployed contract:** `0x13343510C2713aDADb8E6F3c8b2951100BA97149`
- **License:** MIT

---

## Why this is a primitive, not a demo

| Rejected pattern | How PledgeCheck avoids it |
|---|---|
| Thin LLM wrapper | The LLM ruling is folded into real state: charters, quotas, TTLs, a freeze switch and an immutable decision log. |
| Format-only validator | The validator agrees only when its **independent verdict matches** (`ALLOW`/`BLOCK`/`ESCALATE`) **and** its confidence falls in the same band — it checks the *decision*, not the JSON shape. |
| One-off "AI decides X" | Rules, quota and TTL are all parameters; one deployment gates many agents and many policies. |
| Hidden non-determinism | Remove the jury and the primitive is meaningless — the semantic ruling is the core. |

## Public API

| Method | Kind | Purpose |
|---|---|---|
| `register_charter(rules, max_allows, ttl_secs) -> charter_id` | write | Create a charter. `max_allows=0` = unlimited, `ttl_secs=0` = never expires. |
| `authorize(charter_id, action) -> verdict` | write | Rule on a proposed action. Returns `ALLOW` / `BLOCK` / `ESCALATE`. |
| `freeze(charter_id)` / `unfreeze(charter_id)` | write | Owner-only kill switch. |
| `get_charter(charter_id) -> json` | view | Charter state + allow/block tallies. |
| `get_decision(decision_id) -> json` | view | A single immutable ruling. |
| `get_charter_count()` / `get_decision_count()` | view | Totals. |

## How consensus is used

`authorize()` runs a non-deterministic block through
`gl.vm.run_nondet_unsafe(leader_fn, validator_fn)`:

- **`leader_fn`** prompts the node's LLM to judge the action against the charter
  rules and returns a normalized `{verdict, confidence, reason}` JSON.
- **`validator_fn`** re-runs its *own* independent judgement and returns `True`
  only if the leader's **verdict matches** and its **confidence band** matches
  (`<40`, `40–79`, `>=80`). Disagreement on the decision fails consensus.

Unmappable or missing verdicts fail safe to `ESCALATE` (never a free `ALLOW`).
Deterministic gates — frozen, expired, or quota-exhausted charters — short-circuit
to `BLOCK` with no LLM call, so cost and consensus load only happen when a real
judgement is needed.

## Example

```text
register_charter(
  rules = "The agent may only post educational content about blockchain. "
          "It must never ask a user for a password or seed phrase, and must "
          "never promote a token sale.",
  max_allows = 100,
  ttl_secs   = 86400)              -> "0"

authorize("0", "Post: a plain-English explainer on how validators reach consensus.")
   -> "ALLOW"
authorize("0", "DM: send me your 12-word seed phrase to verify your wallet.")
   -> "BLOCK"
```

## Build & test

```bash
python3 -m pytest tests/ -q          # 10 tests, direct-mode (mocked LLM)
```

## Deploy

```bash
source ~/.genlayer/env.sh            # exports GENLAYER_PRIVATE_KEY
python3 scripts/deploy.py --check-only   # validate schema, no spend
python3 scripts/deploy.py                # deploy to studionet
```

## GenLayer conventions honoured

`# v0.2.16` pin, `Contract(gl.Contract)`, `bigint` for all stored numbers,
`TreeMap[str, ...]` storage, `@allow_storage @dataclass` structs, every
`gl.nondet.*` call inside an inner function, ASCII-only source, SDK import on
line 3. See [`contracts/pledgecheck.py`](contracts/pledgecheck.py).
