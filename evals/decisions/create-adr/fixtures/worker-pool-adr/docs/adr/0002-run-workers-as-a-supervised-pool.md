---
id: ADR-0002
title: Run workers as a supervised process pool
status: accepted
date: 2026-03-10
deciders: [dana]
supersedes: []
superseded-by: []
related: [ADR-0001]
research: []
tags: [queue, workers, operations]
---

# ADR-0002: Run workers as a supervised process pool

## Context and Problem Statement

Invoice volume outgrew a single `run_forever` loop, and a worker that hangs on one invoice
stops the whole queue. The billing service needs several workers on one host, restarted when
they die, with configuration and logs an operator can find without reading code.

## Decision Drivers

- A hung or crashed worker must not stop other invoices from running
- Operators deploy with a config file and read logs from stdout; there is no log agent
- A deploy must not cut an invoice off halfway through its handler

## Considered Options

1. **A supervised pool of worker processes** — one parent forks N workers and restarts any that exit
2. **Threads in one process** — a thread per worker
3. **One systemd unit per worker** — the init system supervises each worker

## Decision Outcome

Chosen option: **A supervised pool of worker processes**, because a crashed or hung process is
isolated from its siblings and the parent can restart it, which threads cannot offer and which
one unit per worker gives only at the cost of templated units on every host.

The decision includes these specifics:

- **The pool size is `workers` in `jobqueue.toml`**, default 4. The parent reads `jobqueue.toml` once at start; changing it takes a restart.
- **Workers log one JSON object per line to stdout**, with the job id on every line.
- **SIGTERM drains the pool.** The parent stops handing out jobs and waits up to 30 seconds for running handlers before killing the workers.

## Consequences

### Positive

- One stuck invoice no longer blocks the rest
- Configuration and logs live where operators already look

### Negative

- A config change needs a restart
- The parent is a single point of failure on each host

### Risks

- A handler that ignores SIGTERM is killed after 30 seconds; watch for `drain timeout` in the logs

## Pros and Cons of the Options

### A supervised pool of worker processes

- Good: crash isolation; one parent to deploy
- Bad: a parent process to maintain

### Threads in one process

- Good: least code
- Bad: one hung handler can wedge the interpreter

### One systemd unit per worker

- Good: the init system does supervision
- Bad: a templated unit per worker on every host

## Implementation Notes

The pool lives in `jobqueue/pool.py`. Invariants: configuration is read only from
`jobqueue.toml`; nothing logs to a file; every running handler gets the full drain window on
SIGTERM.

## References

- ADR-0001 — the queue these workers consume
