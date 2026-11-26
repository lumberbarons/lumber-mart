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
which removes a job from Redis before its handler runs, so a worker that dies mid-handler loses
the invoice. ADR-0001 chose Redis lists and named "Invoice jobs must not be lost" as a driver;
the code does not meet it. The question is how a job stays recoverable until its handler has
finished.

## Decision Drivers

- Invoice jobs must not be lost when a worker dies (ADR-0001), which today's `BLPOP` dequeue violates
- No new infrastructure: ADR-0001 rejected a dedicated broker because the team runs only Redis
- Producers call `enqueue` from several billing services; changing them all is a cross-team release

## Considered Options

1. **Move, then acknowledge** — `BLMOVE` the job onto a per-worker processing list and remove it only after the handler finishes
2. **Redis Streams with consumer groups** — acknowledge entries with `XACK`
3. **RabbitMQ** — a broker with acknowledgements
4. **Do nothing** — keep `BLPOP` and correct the README

## Decision Outcome

Chosen option: **Move, then acknowledge**

In the context of invoice jobs on Redis lists, facing jobs lost when a worker dies, we chose to
keep each job in Redis until its handler has finished, over Redis Streams, RabbitMQ and doing
nothing, so that a crash cannot lose an invoice, accepting that a job may run more than once.

Streams would give acknowledgement too, but every producer's `enqueue` would change, which the
cross-team driver rules out, and pending-entry recovery would still be needed. RabbitMQ fails the
no-new-infrastructure driver that ADR-0001 set. Doing nothing keeps losing invoices, which
fails the first driver; correcting the README would only make the loss documented.

## Consequences

### Positive

- A worker crash no longer loses an invoice, and the README's promise becomes true
- Producers are unchanged; only the worker side of the queue moves

### Negative

- A job whose worker died is run again, so it can run twice; handlers must tolerate that
- Jobs left on a dead worker's processing list need something to return them to the queue, which is new code to run and watch

### Risks

- A worker that is slow rather than dead could have its job returned while it is still running, causing a duplicate run. Duplicate `invoice.sent` events for one invoice id are the signal.

## Implementation Notes

Invariants future changes must keep:

- No code removes a job from Redis before its handler has returned or the job has been dead-lettered.
- Every handler is safe to run twice for the same invoice id.

Accepting this puts today's `dequeue` in violation until it is changed; that change is the first piece of work. How orphaned jobs are detected and returned is for the spec.

Revisit if duplicate runs appear in the `invoice.sent` metrics, or if billing adopts Redis Streams elsewhere so that the producer change is no longer a cross-team release.

## References

- ADR-0001 — Redis lists, the job-loss driver, and the rejection of a dedicated broker
- `jobqueue/queue.py` — the `BLPOP` dequeue this replaces
