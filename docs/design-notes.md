# Design notes

Decisions taken so far, and open questions to revisit later.

## Decisions

| Topic | Decision | Why |
| --- | --- | --- |
| Past vs. upcoming events | Derived from `starts_at` at query time; no stored `completed` flag | A stored flag goes stale unless a job keeps updating it |
| Capacity / overselling | `tickets_booked` counter, updated with one atomic conditional `UPDATE`; DB `CHECK (tickets_booked <= capacity)` as backstop | Correct under concurrent bookings without app-level locks |
| Deleting events | Soft cancel (`cancelled_at`) | Booked users keep their booking history and can see the event was cancelled |
| FK delete behaviour | `RESTRICT` on all foreign keys | Bookings are records we keep. `CASCADE` would also leave `tickets_booked` wrong, since the DB can't run app logic |
| Retries / idempotency | Required `Idempotency-Key` header on bookings, unique per `(user_id, key)` | A retried request (e.g. after a network drop) returns the original booking instead of creating a second one |
| Repeat bookings | Allowed: one row per booking | A business choice; deliberately separate from idempotency |
| User identity (for now) | `X-User-Id` header read by one dependency | Real auth can replace that one dependency later |
| IDs | Integer primary keys | Simple to demo; consider UUIDs once auth exists |
| Test database | Real PostgreSQL via testcontainers, not SQLite | Locking, `timestamptz`, constraints and migrations must behave like production |
| Seed data | Dev-only script, run via Compose; never by the image; refuses `ENVIRONMENT=production` | Build one image, promote it unchanged through dev → staging → prod |

## Open questions / later

- **Deleting a user:** delete or anonymize (GDPR right to erasure, legal retention of booking records)? Their upcoming bookings would need to release their tickets first.
- **Deleting an event owner:** transfer their events to another owner, or cancel them first? An event must never be left without an owner.
- **User management & auth:** real authentication, and roles (owner vs. attendee).
- **Booking cancellation by users:** must decrement `tickets_booked` in the same transaction.
- **Per-user ticket limit** per event.
- **Notifying booked users** when an event is cancelled.
- **Idempotency for `POST /events`** (same mechanism as bookings).
- **Idempotency key retention:** keep forever on the booking row, or expire after N days?
