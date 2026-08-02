# Roadmap

CLASS: law
RECOMPUTED BY: nothing. The owner decides what gets built. The measurements
below are dated and stay dated: re-measuring may change the plan, but only the
owner changes this file.

What to build. Written 2026-08-02 from measurements taken across the live
system on 2026-08-01 by four roles, and designed against them.

**This file is the plan. GitHub Issues is the work.** Every item below is a
ticket and the ticket is canonical: if this file and an issue disagree, the
issue is right. What lives here is direction, sequencing and the reasoning for
both, which does not belong in a ticket. What a thing *is* lives in its ticket.

---

## The end state

**Lineage is a machine that turns a term and a field into an evidence-backed map
of how that term developed: about twenty minutes, a couple of dollars, for
anyone who asks, without the owner reading the result first. What makes it a
product rather than a demonstration is that each map arrives with its own
honestly computed account of how good it is — how much of it is quote-verified,
how much evidence it had to discard, how lopsided its structure came out, how
recent its sources are, and what the run cost. A stranger can decide whether to
trust one particular map without having to trust us.**

The product is the generator. The published maps are receipts, not merchandise
(decision 26 and the Product Owner's framing: *"we are simply here to provide
the capability"*).

### The qualification that shapes everything below

**Today Lineage verifies its evidence and asserts its shape.** A quote is
string-matched against the paper and that check is real. Everything else on the
screen — which cluster a paper fell into, which thread it rides, what type of
relationship an arrow carries and which way it points, how large a dot is,
whether it wears a turning-point ring — is generated, unverified, and rendered
in the same visual register as the verified part.

Measured, 2026-08-01: **610 of 610 edge quote slots on the `embedding` map are
exactly that paper's own definition quote**; 287 `attention` edges carry 79
distinct quote strings between them, one appearing 43 times. Product rule 1 is
satisfied literally while the quotes cannot discriminate `extends` from
`contests`.

That difference is safe while somebody reads every map before it is published,
and stops being safe at the moment the platform decision takes effect.

**The design response is not to prove the shape correct.** That needs a labelled
ground truth, which is on `CLAUDE.md`'s OUT list and stays there, and the domain
expertise the Product Owner has explicitly disclaimed. The response is that
**the shape publishes its own properties, computed from the map's own rows, with
no ground truth involved.** A reader who is told that 62% of a map's links sit
between the same pair of concept-states while disagreeing about what happened
there knows what they are holding. That is a capability statement rather than a
curatorial one.

---

## Key feature drops

Each is a GitHub issue and the issue is canonical. What follows is the plan;
what a thing *is* lives in its ticket.

| | | |
|---|---|---|
| **F1** | The re-checkable stamp | [#29](https://github.com/rgok001/Lineage/issues/29) |
| **F2** | The map report | [#30](https://github.com/rgok001/Lineage/issues/30) |
| **F3** | Remove Stage D's same-cluster discard | [#31](https://github.com/rgok001/Lineage/issues/31) |
| **F4** | Versioned maps | [#32](https://github.com/rgok001/Lineage/issues/32) |
| **F5** | Corpus recency | [#33](https://github.com/rgok001/Lineage/issues/33) |
| **F6** | A requester can see the state of their own request | [#34](https://github.com/rgok001/Lineage/issues/34) |
| **F7** | Sources beyond arXiv | [#35](https://github.com/rgok001/Lineage/issues/35) |
| **F8** | A map has an owner, and can be private | [#36](https://github.com/rgok001/Lineage/issues/36) |
| **F9** | Bring your own corpus | [#37](https://github.com/rgok001/Lineage/issues/37) |

**F1 is the one that matters most.** No verification stamp in the database can be
re-checked from stored data, because the text it was matched against is not
stored. That is the project's defining incident one level up, and on a platform
where strangers generate maps, a tick only our worker can substantiate is not
evidence, it is a claim about evidence.

## Quality-of-life enhancements

| | | |
|---|---|---|
| **Q1** | Parallelise Stages B and D | [#38](https://github.com/rgok001/Lineage/issues/38) |
| **Q2** | A preview before a run | [#39](https://github.com/rgok001/Lineage/issues/39) |
| **Q3** | Show the reproducibility facts | [#40](https://github.com/rgok001/Lineage/issues/40) |
| **Q4** | Print confidence at the resolution it has | [#41](https://github.com/rgok001/Lineage/issues/41) |
| **Q5** | Node labels ask for the common thread rather than a name | [#42](https://github.com/rgok001/Lineage/issues/42) |
| **Q6** | Proper 403s instead of fail-closed 500s | [#43](https://github.com/rgok001/Lineage/issues/43) |
| **Q7** | A marker at the timeline's horizon | [#44](https://github.com/rgok001/Lineage/issues/44) |
| **Q8** | Corroboration counts | [#45](https://github.com/rgok001/Lineage/issues/45) |

## Sequencing

**The rule: fix the generator before strangers use it; make the map answer for
itself before you stop reading it; only then open the door.**

**Phase 0 — the generator stops lying about its own runs.** About a week, $0.
Backlog items 2, 3, 7, 27 and the run-level spend cap. Every one produces a
plausible wrong result and reports success, and every one used to be caught by
the owner looking at the output.

**Phase 1 — the map answers for itself.** About two weeks, $0 to build. F1, then
F2, then F3, then the front-page honesty fixes (backlog 4, 5, 6, 9, 25 and the
verified-quote count). F1 first because F2's headline numbers are verification
fractions, and a fraction computed from stamps that cannot be re-checked is a
check agreeing with itself. F2 before F3 because F3 needs a before-and-after
measurement and F2 is the instrument.

**Phase 2 — the door opens.** About two weeks. F4, then F5, then F6.

**Phase 3 — quality of life.** Q1 after the spend cap, then the rest as they fit.

Five to six weeks of one person, with F4 the one item where a week could become
two.

---

## What we will not build, and why

- **Email notifications.** Blocked on a verified domain, and solved 90% by F6 in
  an hour.
- **A better clustering threshold.** Four recalibrations on this project moved
  nothing. F3 removes the place where clustering error does damage.
- **A node-to-node relationship view.** 62% of edges would render as a single
  arrow standing for contradictory evidence. The measurement exists to stop this
  being built.
- **Anything further in the workbench.** Zero curatorial operations have been
  performed in the product's life, and curation is not the product. Keep what
  exists; add nothing.
- **A formal eval harness or golden set.** Stays on the OUT list. F2 is not one.
- **Requester billing**, until the trigger in decision 26 fires. Building it now
  is scaffolding for later.
- **Non-arXiv sources before F2 ships.** No longer forbidden — the contradiction
  was resolved on 2026-08-02 in favour of expanding, and it is now F7. What stays
  out is building it early: a source that extracts badly produces maps that fail
  grounding, and F2's report is what makes that visible instead of surprising.

---

## Open questions

1. **Who pays for a trace.** *Answered: the owner, until the product earns
   organic usage — decision 26.*
2. **Does the OUT list still forbid non-arXiv sources?** *Answered 2026-08-02:
   no. Sources expand. Removed from `CLAUDE.md`'s OUT list, filed as F7, and
   sequenced after F2 so its effect on extraction quality is measurable rather
   than assumed.*
3. **Is a stranger's map public by default?** *Answered 2026-08-02: no. Whoever
   paid owns it, private by default, with an option to publish — decision 27 and
   F8. Request notes and sense glosses are the author's and are not published.*
4. **Does product rule 3's "users can curate" apply to the requester, or only to
   the owner?** *Answered 2026-08-02: the requester. The payer curates their own
   map, so rule 3 is satisfied under the platform reading rather than only when
   "users" means the owner — decision 27.*
5. **Is "about fifteen minutes" a promise or a description?** Measured runs are
   23.3 and 18.3. If a promise, Q1 moves into Phase 1.
6. **How much does the shared extraction cache actually save?** Only Stage B is
   cached; clustering, edges, magnitude, threads and claims are paid again per
   map. Per-stage spend is recorded nowhere, so the fraction of a map's $1.47 to
   $1.92 that the cache avoids is unknown. The platform's cost story rests on it,
   and measuring it is free.
