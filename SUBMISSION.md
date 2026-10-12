# Portal submission — PledgeCheck

- **Track:** Builder
- **Contribution Type:** Intelligent Contracts
- **Contribution Date:** 2026-10-12

**Title**
PledgeCheck - consensus-graded authorization gate for AI agents

**Notes / Description (<= 1000 chars)**
PledgeCheck is a reusable GenLayer primitive that authorizes an AI agent's action BEFORE it runs. An owner registers a plain-language charter (the rules the agent must keep); the agent calls authorize(charter_id, action) and a decentralized LLM jury rules ALLOW / BLOCK / ESCALATE on the SPIRIT of the charter. Consensus is on MEANING: each validator re-runs its own judgement and agrees only if the verdict matches and the confidence lands in the same band - not on JSON shape. Each charter also has a hard allow-quota, a time-to-live and an owner freeze switch, all enforced deterministically with no LLM spend, so it is also a rate- and lifetime-bounded capability gate. Rules, quota and TTL are parameters, so one deployment guards many agents and policies. State: charters + immutable decision log. 10 passing gltest tests. Deployed to studionet.

**Evidence**
- Repo: https://github.com/phu1271997/pledgecheck
- Contract (studionet, chain 61999): `0x13343510C2713aDADb8E6F3c8b2951100BA97149`

**Taxonomy**
- Primary: AI & Agents
- Tag 1: AI Policy Enforcement
- Tag 2: Autonomous Execution
