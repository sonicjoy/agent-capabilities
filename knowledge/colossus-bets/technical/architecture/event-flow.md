<!-- Generated from Colossus KB graph; edit via kb.py, not here -->

# Event Flow Architecture

**Added**: 2026-01-23
**Id**: `event-flow-architecture`

> Sport event status changes flow from the console through the database and Kafka to the engine (enginelinux).

## Sport Event History Flow

Sport event status changes flow: Console (consolelinux) → Database → Kafka → Engine (enginelinux).

**Flow**:
1. Console operators set sport event status (NOT_STARTED → IN_PLAY → COMPLETED → OFFICIAL)
2. Console creates `sport_event_histories` record
3. Console emits event to Kafka topic
4. Engine consumes Kafka message and processes the event

**Key points**:
- Engine does NOT create `sport_event_histories` - it only reads them
- Engine receives events reactively via Kafka
- `updated_by` field shows who created the record (operator email or `feed-processor`)

**Racing event status flow**: `NOT_STARTED → IN_PLAY (STARTED) → COMPLETED → OFFICIAL`

The OFFICIAL status is typically set after results are confirmed ("Weighed in" for horse racing).
