# Design: an actor on every curatorial edit, and the basis for it

**Status: approved by the Product Owner, 2026-07-31. Not yet implemented.**
Architect's design; the open question in section 6 has been decided and the
answer is recorded there.

## 1. The problem

`genealogies.user_edits` records what changed and when, and only sometimes who.
Web edits go through `requireOwner()` and carry a GitHub login in `by`. CLI edits
carry no actor at all, so anything holding the repo `.env` can merge, rename or
delete a node and leave a record that names nobody. When the as-built claimed the
`embedding` map had been curated and the owner said otherwise, the data could not
settle it. `user_edits` happened to be empty, so the question dissolved; had it
held a single entry, nothing in the system could have said whether a human did
that or a script did.

Two live defects found while verifying the ticket:

`pipeline/restore_genealogy.py:45` writes `{"op": "restore", ..., "by": "cli"}`.
That literal string sits in the same key as authenticated GitHub logins, and
`AuditTrail` renders it "by cli", indistinguishable from "by rgok001". The
namespace has already collided once, unnoticed, in the recovery script written
during incident 4.

`app/app/g/[id]/evidence/page.tsx:260` prints "(cli)" when `by` is absent. That is
a positive claim about origin manufactured out of an absence. Every pre-existing
entry currently renders as an assertion that the command line made it, which
nobody knows.

## 2. The design

**One new key, never both.** `by` is reserved, from now on, for an actor a third
party authenticated: a GitHub login obtained from a session. A new sibling key
`by_asserted` holds a name the running process asserts about itself. An entry
carries `by`, or `by_asserted`, or neither. `user_edits` is JSONB, so no
migration.

The fail-safe property is why this is preferred to the alternatives: any reader
that has not been updated, in the app or the exports or a future script, sees no
`by` on a CLI entry and degrades to "unattributed". It can never degrade to
"authenticated". That is `isOwner()` failing closed, applied to attribution.

**Files that change.**

`app/lib/genealogy.ts`. `UserEdit` gains `by_asserted?: string`. `recordEdit()`
changes its fourth parameter from `by?: string` to `by: Viewer` (from
`lib/authz.ts`) and writes `by: by.login`. This is the load-bearing part: a
`string` is a convention any caller can satisfy with any text, while a `Viewer`
can only be obtained from `getViewer()` or `requireOwner()`, so the compiler
rather than a comment keeps unauthenticated text out of `by`. Six call sites in
`app/lib/actions.ts` change from `who.login` to `who`.

`pipeline/workbench.py`. `record()` takes the actor and writes `by_asserted`. The
value is `LINEAGE_ACTOR` from the environment if set, otherwise `user@host` from
`getpass.getuser()` and `socket.gethostname()`. An `actor()` helper belongs in
`pipeline/common.py` beside `env()`, because three scripts need it.

`pipeline/restore_snapshot.py:114` and `pipeline/restore_genealogy.py:45` call the
same helper. The second is a live fix: `"by": "cli"` becomes
`"by_asserted": actor()`.

`app/app/g/[id]/evidence/page.tsx`, `AuditTrail`. Three renderings where there are
now two, and the "(cli)" fabrication goes. Proposed copy, the Product Owner's to
adjust:

- `by rgok001 · signed in`
- `by ravi@laptop · from the command line, name not verified`
- `actor not recorded`

No stamp, and no colour borrowed from the verified tier. The green check means
one thing in this product and must not acquire a second.

**Two consequences elsewhere, in scope because they are the same defect.**
`app/lib/export.ts:171` and `pipeline/export_related_work.py:145` both write
"Curated by hand: N workbench edit(s) applied" into a document that lands in a
researcher's paper. That sentence claims human agency from a count that cannot
support it, which is the claim the as-built already had to retract about
`embedding`, now travelling into someone else's manuscript. It becomes a
statement of the count plus the actors where they are known, with their basis,
and drops "by hand" when no actor is known. Incident 11's lesson is that a fix
scoped to the symptom gets applied at the width of the symptom; the class here is
"an unsupported claim about who curated a map", and the export is where that
claim does the most damage.

`pipeline/snapshot_map.py:106` prints each edit and deliberately does not print an
actor, with a comment saying there is never one to print. It prints it now. That
script is the forensic tool for exactly the question this ticket exists to answer.

**Existing entries are not touched.** No backfill, no inference, no default. An
entry written before this ships carries neither key and renders "actor not
recorded", which is the complete truth about it. This also buys an invariant
rather than a convention: after this ships both write paths always populate one
key, so an entry with neither is by construction a legacy entry, and that set is
fixed at deploy time and must never grow.

**Against the five recurring faults.** Nothing here is a derived value that can
age; an actor is a fact about an event at the moment it happened, and nothing can
change it. The one derived claim in the blast radius, the export's "curated by
hand", is the thing being fixed. There is no check that agrees with itself: the
separation is enforced by a type whose only source is a session. There are no
thresholds. Nothing is destroyed or rewritten; every change is additive to future
writes. The one fallback, `LINEAGE_ACTOR` unset falling back to `user@host`, has
the global sanity check named in section 4.

## 3. What it costs

No LLM spend. No migration. No rewrite of any stored row, so no risk to the two
live maps: their `user_edits` are read and rendered differently but never
written. Half a day, most of it copy and the six call sites.

The one risk worth naming: `LINEAGE_ACTOR` is free text supplied by whoever holds
`.env` and it renders on a public page. React escapes it, so this is not an
injection concern, and only people who can already delete the map can set it. But
it is a label, not a credential, which is precisely why it lives in its own key.

## 4. How it will be verified

Five checks, and what each would falsify.

1. Run `python pipeline/workbench.py <scratch concept> rename n1 "x"` and
   `SELECT jsonb_pretty(user_edits)`. The new entry must carry `by_asserted` and
   must not carry `by`. A `by` on that entry falsifies the whole design.
2. Rename a node as the owner in the web workbench. The entry must carry `by` and
   no `by_asserted`.
3. `grep -rn '"by"' pipeline/` must return zero write sites. That is the
   structural check: the app becomes the only writer of `by`, and the only value
   it can write comes from a session.
4. Before deploying, run
   `SELECT id, concept, jsonb_path_query_array(user_edits, '$[*].by') FROM genealogies`
   to find any surviving `"by": "cli"` from the incident-4 restore. If one exists
   it is a real misrepresentation in live data, and whether to leave it (it is
   history) or correct it by hand is the Product Owner's judgement, not something
   a migration should do silently.
5. `md5(user_edits::text)` on both live maps before and after deploy must be
   identical. Any change means something rewrote history.

Then the reader test, which is the one that matters. Build a fixture map holding
one entry of each of the three shapes and show the audit trail to someone who has
not read this document. They must be able to say which edit was made by someone
signed in. If the asserted and the authenticated entries read the same to them,
the copy is wrong even though the data is right.

## 5. Considered and rejected

- **One `by` plus a sibling `by_verified: boolean`.** Fails open: any reader that
  ignores the flag shows an asserted name as authenticated.
- **A structured `actor: {name, basis}` object.** Every existing reader loses `by`
  at once and must change in lockstep, and it scaffolds for bases that do not
  exist.
- **A required `--as NAME` flag on every CLI command.** Friction across a long
  curation session breeds one junk constant, which then looks deliberate; it also
  breaks the invocations in the README and the module docstring.
- **OS username only, no override.** On Render the container user is noise, and
  an operator should be able to say who they are.
- **Authenticating the CLI properly, with a token or device flow.** It would make
  a CLI edit look as trustworthy as a web one, which is a lie about a tool anyone
  holding `.env` can run. Label the trust level; do not fake it. Adjacent to the
  accounts scope on the OUT list besides.
- **Backfilling legacy entries as "cli".** That is the fabrication this ticket
  exists to stop.
- **Refusing CLI edits altogether.** The pipeline is CLI-first by rule and the CLI
  workbench predates the web one.
- **A verified-style stamp on authenticated actors.** The green check means a
  quote was string-matched against extracted text and must keep meaning only that.

## 6. Open questions

**Decided (Product Owner, 2026-07-31): the audit trail stays public.** A visible
record of what a human changed is the workbench claim made good, and hiding it
would leave a reader unable to tell a curated map from a raw one. The operator
name is published as a consequence, understood as a label rather than a
credential.

Proceeding without asking: the exact wording of the three renderings is the
Product Owner's to adjust, and the as-built gets a decision-record entry saying
that `by` is authenticated, `by_asserted` is not, neither is present on entries
predating this change, and that absence is never rendered as a claim about origin.
