# Design notes

Decisions taken so far, and open questions to revisit later.

## Decisions

| Topic | Decision | Why |
| --- | --- | --- |
| Past vs. upcoming events | Derived from `starts_at` at query time; no stored `completed` flag | A stored flag goes stale unless a job keeps updating it |
| Capacity / overselling | `tickets_booked` counter, updated with one atomic conditional `UPDATE`; DB `CHECK (tickets_booked <= capacity)` as backstop | Correct under concurrent bookings without app-level locks |
| Deleting events | `DELETE` performs a soft delete: sets `cancelled_at` and cancels all confirmed bookings in one transaction. Only before the event starts (else `409`) | Meets the "owner can delete" requirement without erasing booking records ([AIP-164](https://google.aip.dev/164)) |
| Ticket counter invariant | `tickets_booked` = sum of quantities of *confirmed* bookings | One rule for every state change: booking, user cancellation, event cancellation |
| Event status | Only `cancelled` is stored. `scheduled`, `sold_out`, `past` are derived at read time | Derived states can never go stale |
| FK delete behaviour | `RESTRICT` on all foreign keys | Bookings are records we keep. `CASCADE` would also leave `tickets_booked` wrong, since the DB can't run app logic |
| Retries / idempotency | Required `Idempotency-Key` header on `POST /events` and bookings, unique per user. Replays return the original resource (`Idempotent-Replayed: true`); same key with a different body → `422` | A retried request (e.g. after a network drop) never creates a duplicate. The key is stored on the resource, so it is written in the same transaction |
| Error format | [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) Problem Details (`application/problem+json`) for every error | One predictable error shape; services raise domain errors and stay HTTP-agnostic |
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
- **Idempotency key retention:** keep forever on the booking row, or expire after N days?
