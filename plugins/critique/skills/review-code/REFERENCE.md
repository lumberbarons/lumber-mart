# Example Output

This reference shows the expected format and level of detail for a code review report.

---

## Example Report

```
Code Review for src/order

4 files reviewed, 3 issues found (1 P1, 1 P2, 1 P3).

### 1. [P1] Refund authorization is decided from a client-supplied header
**Location:** src/order/auth.go:15

`RequireAdmin` reads `X-Admin` off the inbound request, and `POST /order/refund` is
gated on it. Any customer can set that header themselves, so the one endpoint that
moves money back out is unprotected. Every future check built on `RequireAdmin`
inherits the bypass.

**Fix:** Derive the role from a verified credential — a signed session token or a
server-side session lookup — returning `(Role, error)` so an authentication failure is
distinguishable from an authenticated non-admin. Read the role from request context
populated by authentication middleware, never from a header.

**Done when:** No function derives a role or permission from `r.Header.Get`, and a
request carrying only `X-Admin: true` receives 403 from `POST /order/refund`.

### 2. [P2] Discount rules are inlined in the HTTP handler
**Location:** src/order/handler.go:23

`handleCheckout` parses the request and then computes volume discounts inline, even
though `pricing.go` already owns that ladder. Adding a second entry point — the queue
consumer planned for bulk imports, or a CLI — means re-implementing the tiers, and the
two copies drift silently: the quote endpoint and the checkout endpoint would show
different totals with no error anywhere.

**Fix:** Call `pricing.LineTotalCents(unitCents, qty)` from the handler and delete the
inline tier ladder at handler.go:23-31.

**Done when:** `handler.go` contains no discount arithmetic, and both the checkout and
quote paths reach their totals through `pricing.go`.

### 3. [P3] `processOrder` does not distinguish itself from its sibling handlers
**Location:** src/order/handler.go:61

`Routes` registers `processOrder`, `refund` and `quote`. Two name the operation; the
first names nothing, so the doc comment has to supply what the name omits. A maintainer
scanning `Routes` for the order-placement endpoint has to read the body to be sure.

**Fix:** Rename to `handleCheckout`, matching the operation it serves, and update the
registration in `Routes`.

**Done when:** `processOrder` no longer appears in `handler.go` and `POST /checkout`
dispatches to `h.handleCheckout`.
```

---

## Format Rules

### Start with a count line

`N files reviewed, M issues found (severity breakdown).` The header count reflects the
*reported* findings.

### Findings use H3 headers with a priority tag, then Location, Fix, and Done when

```
### 1. [P2] Short statement of the design problem
**Location:** src/order/service.go:87

Explanation naming the change this design would break.

**Fix:** Concrete prescription — for API issues, the exact signature.

**Done when:** A criterion checkable by reading the diff.
```

### Only show issues found — no passing rows

Do not list items that passed review. The one exception is the verdict below: on code
that holds up, a sentence or two saying so is not a passing row, it is the finding-free
result stated plainly.

### When the code is sound

A near-empty report still needs a verdict, or the reader cannot tell a careful review
from a cursory one:

```
Code Review for pricing/

4 files reviewed, 0 issues found.

The design holds up. Rates are injected through a protocol rather than fetched, so the
conversion logic is testable without a network; each module has one job; and the error
hierarchy gives callers a single type to branch on with the offending value attached.
Nothing here rises to a finding.
```

### No tables

Do not include summary tables or issue tables. Findings are the only output.

### Truncation footer when the cap kicks in

When findings exceed the reporting cap (see SKILL.md), end with a single-line footer:

```
Note: 7 additional findings omitted (4 P2, 3 P3) — re-run after addressing these to surface what remains.
```

The footer is omitted when all findings fit under the cap. The footer count reflects the
*omitted* tail.

---

## Pattern slugs

The `pattern` field of a findings file (see [FINDINGS.md](FINDINGS.md)) names a finding's
root cause. Consumers use it as part of a finding's identity across runs, so it has to be stable
between them — a slug that drifts from one phrasing to another reads as a new finding and gets
filed twice. Pick from this list; use `other-<slug>` when nothing fits, and treat a recurring
`other-` slug as a sign this list needs extending.

```
api-design
dead-code
duplicated-logic
error-handling-strategy
leaky-abstraction
single-responsibility
unclear-naming
untestable-seam
```
