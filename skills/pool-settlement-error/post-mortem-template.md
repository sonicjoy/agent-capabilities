# Post-Mortem: Pool [POOL_ID] Wrong Settlement

**Pick'em / [TYPE_CODE] — Internal Use Only**

| Field | Value |
|-------|-------|
| Date of incident | [DATE] |
| Environment | [UK/US/STAGING] pool [ID] / commingled [ID] |
| Status | [Root cause identified / correction applied / pending] |
| Prepared | [DATE] |
| Distribution | Internal — Ops, Engineering, Product |

---

## Executive Summary

[2–3 sentences: what settled wrong, how many legs, payout impact.]

**Root cause:** [One sentence — e.g. fantasy approval gate, unapproved pending approvals.]

**Not the cause:** [e.g. SportsData lag, manual_override, engine bug.]

---

## Affected Pool & Fixtures

| Item | Value |
|------|-------|
| UK pool | |
| US commingled pool | |
| Pool type | |
| Fixtures | |
| Markets / Legs | |

---

## Wrong Legs

| Leg | Player | Metric | Line | Settled | Correct | Result |
|-----|--------|--------|------|---------|---------|--------|
| | | | | | | UNDER → OVER |

**Corrected results string:** [e.g. 2/1/2/1/1/2/2/1/2/2] (was [original])

---

## Timeline (UTC)

| Time | Event | [Player/metric columns] | Tote |
|------|-------|-------------------------|------|
| | STARTED | | |
| | Approval created | | |
| | stats_feed correct value | | |
| | Last FOU_UPD | | |
| | OFFICIAL | | wrong |

---

## Fantasy Approvals

| ID | Leg | Player | Proposed value | Created | Approved |
|----|-----|--------|----------------|---------|----------|
| | | | | | |

---

## Root Cause

### Primary
[Describe mechanism — e.g. FantasyOverUnderMetricsProcessor creates approval instead of FOU_UPD when threshold+buffer crossed.]

### Secondary / aggravating
[e.g. ops queue not cleared; low OU line; duplicate sport_event_player.]

### Control case (if any)
[Leg that worked correctly and why.]

---

## What We Ruled Out

| Hypothesis | Verdict | Evidence |
|------------|---------|----------|
| SportsData lag | | |
| manual_override | | |
| settle_manually | | |
| Engine settlement bug | | |

---

## Data Flow

```
SportsData → stats_feed → cbstatsfeed → [approval gate?] → FOU_UPD → tote → OFFICIAL
```

[Where the break occurred.]

---

## Impact

| Metric | Value |
|--------|-------|
| Wrong leg outcomes | /10 |
| Tickets with payout change | |
| Net payout delta | |
| Commingled exposure | |
| Offer regen offGenId | |

---

## Remediation

### Completed
- [ ]

### Pending
- [ ]

---

## Recommendations

### Ops
1.

### Engineering (short term)
1.

### Engineering (medium term)
1.

---

## Lessons Learned

1.

---

## Key References

| Resource | ID / Path |
|----------|-----------|
| Pool | |
| stats_feed game | |
| Corrected offer files | |
| ESPN play-by-play | |
