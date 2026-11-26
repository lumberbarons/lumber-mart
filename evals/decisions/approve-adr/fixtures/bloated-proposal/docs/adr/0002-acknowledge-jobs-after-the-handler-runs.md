---
id: ADR-0002
title: Acknowledge jobs only after the handler runs
status: proposed
date: 2026-11-20
deciders: [dana, sam]
supersedes: []
superseded-by: []
related: [ADR-0001]
research: []
tags: [queue, redis, delivery]
---

# ADR-0002: Acknowledge jobs only after the handler runs

## Context and Problem Statement

The README promises at-least-once delivery, but `dequeue` in `jobqueue/queue.py` uses `BLPOP`,
which removes a job from Redis before its handler runs. A worker that dies mid-handler loses the
invoice. ADR-0001 names "Invoice jobs must not be lost" as a driver, and the current code does
not meet it. Finance also wants to query dead-lettered jobs, which they cannot do while the
dead-letter list lives in Redis.

## Decision Drivers

- Invoice jobs must not be lost when a worker dies (ADR-0001)
- No new infrastructure beyond what billing already runs: Redis and the billing Postgres database
- Finance needs to query dead-lettered invoices with SQL
- Recovery must be automatic; nobody is on call for the queue at night

## Considered Options

1. **Reliable queue with `BLMOVE`, heartbeats and a reaper, and dead letters in Postgres**
2. **Redis Streams with consumer groups**
3. **RabbitMQ**
4. **Do nothing**

## Decision Outcome

Chosen option: **Reliable queue with `BLMOVE`, heartbeats and a reaper, and dead letters in Postgres**

Streams would also keep a job until it is acknowledged, but every producer and consumer would
change, and pending-entry recovery needs the same reaper. RabbitMQ fails the no-new-infrastructure
driver. Doing nothing leaves the README's promise false.

The decision includes these specifics:

- **Dequeue moves the job, it does not remove it.** `dequeue` uses `BLMOVE jobs:pending jobs:processing:<worker-id> LEFT RIGHT`. The job is removed from the processing list with `LREM` only after the handler returns or the job is buried.
- **Workers heartbeat.** Each worker writes `jobs:heartbeat:<worker-id>` every 45 seconds with a 30-second TTL.
- **A reaper re-queues orphans.** A reaper process runs every 60 seconds, finds processing lists whose heartbeat key has expired, and moves their jobs back to the head of `jobs:pending`.
- **Jobs carry an attempt count.** A job is dead-lettered after 5 attempts, counting both handler exceptions and reaper re-queues.
- **Dead letters move to Postgres.** `bury` inserts into a `dead_jobs` table in the billing database (`id`, `payload jsonb`, `attempts`, `last_error`, `buried_at`) instead of pushing to `jobs:dead`. The Redis list is drained into the table once and deleted.
- **Operators can requeue dead jobs.** A new `jobqueue requeue --dead` command moves every row in `dead_jobs` back to `jobs:pending` and deletes it; it exits 0 when it requeued something, 3 when the table was empty and 1 on error.
- **Handlers must be idempotent**, keyed on the invoice id, because a re-queued job may already have run.

## Consequences

### Positive

- A worker crash no longer loses an invoice; the README's promise becomes true
- Finance can query dead letters directly
- Operators get a supported way to retry dead jobs

### Negative

- A job can run twice after a crash, so every handler must be idempotent
- The reaper is a new process to deploy and monitor
- `bury` now depends on Postgres being reachable; a Postgres outage stops dead-lettering

### Risks

- A worker stalled longer than the heartbeat TTL has its job re-queued while it is still running. Watch for duplicate `invoice.sent` events.
- The one-time drain of `jobs:dead` could double-insert if it is interrupted; it must run in a transaction.

## Pros and Cons of the Options

### Reliable queue with BLMOVE, heartbeats and a reaper, and dead letters in Postgres

- Good: keeps Redis lists; small change to producers
- Bad: a reaper to run; handlers must be idempotent

### Redis Streams with consumer groups

- Good: acknowledgement built in
- Bad: every producer and consumer changes; still needs a reaper for pending entries

### RabbitMQ

- Good: acknowledgements and dead-lettering built in
- Bad: new infrastructure, which ADR-0001 rejected

### Do nothing

- Good: no work
- Bad: invoices keep being lost on crashes

## Implementation Notes

- `jobqueue/queue.py`: `dequeue` switches to `BLMOVE`; a new `ack(job)` does the `LREM`; `bury` writes to Postgres through `jobqueue/dead.py`.
- `jobqueue/worker.py`: the loop calls `ack` after the handler and starts the heartbeat thread. `MAX_RETRIES` stays 3.
- `jobqueue/reaper.py`: new; runs as its own process under the same supervisor as the workers.
- `jobqueue/cli.py`: new; the `requeue --dead` command.
- Invariants: no code removes a job from Redis before its handler finishes or it is buried; every handler is idempotent on the invoice id; `bury` never writes to Redis.
- Tests: kill a worker mid-handler and assert the job runs again within two reaper intervals; requeue with an empty table and assert exit 3; interrupt the drain and assert no duplicate rows.
- Revisit if Redis Streams adoption elsewhere in billing makes option 2 cheap, or if duplicate runs show up in the `invoice.sent` metrics.

## References

- ADR-0001 — the choice of Redis lists, and the job-loss driver
- `jobqueue/queue.py` — the `BLPOP` dequeue this replaces
