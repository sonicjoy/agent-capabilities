<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# Database-First Debugging Methodology

**Added**: 2026-01-28
**Context**: GitLab issue #143 - MVP withdrawal unit re-allocation bug investigation
**Id**: `database-first-debugging-methodology`

> Always start debugging with database investigation before making code changes or assumptions.

## Principle

**Always start debugging with database investigation** before making code changes or assumptions. The database contains the ground truth about what's actually happening.

## Debugging Sequence

### 1. Database Investigation (FIRST STEP)
Before analyzing code or proposing fixes:

1. **Query the actual pool data**:
   - Pool configuration (sport_code, type_code, status)
   - Leg configuration (leg_order, official status)
   - Market snapshots (favourites, withdrawals, timestamps)
   - Ticket distributions (current unit allocations)
   - Remaining unit histories

2. **Verify actual state vs expected state**:
   - What the database shows (actual)
   - What it should show (expected based on business rules)
   - Identify the discrepancy

3. **Timeline analysis**:
   - When did withdrawals happen?
   - When was favourite set?
   - What was the sequence of events?
   - This helps understand if timing is a factor

### 2. Code Path Analysis
After understanding the database state:

1. **Trace the code path**:
   - Which code path does this pool take? (SEP vs non-SEP, etc.)
   - What conditions are checked?
   - What values are used?

2. **Verify theories against database**:
   - Does the favourite exist in winBins?
   - Are withdrawals correctly identified?
   - Is the favourite set correctly?

### 3. Root Cause Identification
Combine database findings with code analysis:

1. **Match database state to code logic**:
   - Does the code handle this scenario?
   - Are the conditions met?
   - What's preventing the expected behavior?

2. **Document findings**:
   - What was verified in the database
   - What theories were confirmed/refuted
   - What remains to be verified

### 4. Fix Implementation
Only after understanding the root cause:

1. Implement the fix
2. Add tests covering the scenario
3. Verify fix with database queries (if possible)

## Example: Pool 51216 Investigation

### Database Queries Used:
```sql
-- Pool configuration
SELECT id, name, sport_code, type_code, status FROM pools WHERE id = 51216;

-- Leg configuration
SELECT l.id, l.leg_order, l.official FROM legs l WHERE l.pool_id = 51216;

-- Market snapshots (favourites and withdrawals)
SELECT mh.market_snapshot, mh.created_at
FROM market_histories mh
WHERE mh.market_id IN (SELECT market_id FROM legs_markets WHERE leg_id IN (...));

-- Ticket distributions (actual unit allocations)
SELECT td.leg_id, s.bin, s.name, td.units
FROM ticket_distributions td
JOIN selections s ON td.selection_id = s.id
WHERE td.pool_prize_id IN (...);
```

### Findings:
- **Actual**: Withdrawn players have 8 units each (should be 0)
- **Actual**: Favourites have 8 units each (should be 16)
- **Root Cause**: Code condition `legWins.Contains(legFav)` was too strict
- **Fix**: Changed to `!legWithdrawals.Contains(legFav)`

## Benefits

1. **Ground Truth**: Database shows what actually happened, not what we think happened
2. **Timeline Understanding**: See the sequence of events
3. **Theory Verification**: Confirm or refute assumptions before coding
4. **Better Fixes**: Understand the actual problem, not just symptoms
5. **Documentation**: Database queries provide concrete evidence

## Tools

- **MCP Database Tools**: Use `user-staging_db_cbtote` or `user-local_db_cbtote_test` MCP servers
- **SQL Queries**: Direct database access via `execute_sql` tool
- **Key Tables**:
  - `pools`, `legs`, `markets`, `market_histories`
  - `ticket_distributions`, `selections`
  - `remaining_unit_histories`, `sport_event_histories`
