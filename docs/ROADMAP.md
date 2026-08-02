# Roadmap

What to build. Written 2026-08-02 from measurements taken across the live
system on 2026-08-01 by four roles, and designed against them.

**This file is capability. `docs/BACKLOG.md` is defects** — the gap between what
is claimed and what is delivered. The two are kept apart deliberately: a defect
register that absorbs features stops being a list of things that are wrong, and
a roadmap that absorbs defects stops being a list of things to build. Items here
cite backlog numbers where the two touch.

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

### F1. The re-checkable stamp
**The most important item in this document.** No verification stamp in the
database can be re-checked from stored data, because the text it was matched
against is not stored — only a path on one worker's disk. The tick is an
assertion by the pipeline about a file on one machine at one moment.

This is the direct descendant of the project's defining incident, the grounding
check that read its own source and therefore could not fail. On a platform it is
fatal: a tick only our worker can substantiate is not evidence, it is a claim
about evidence.

Migration 015 adds to definitions and edge evidence the matched span offsets, a
digest of the extracted-text file the match ran against, and the extractor
version. A stamp whose digest no longer matches renders as **stale, not
re-checked** — never as verified, and never silently re-anchored to the new
text, which incident 10 established is dishonest.

Unblocks backlog item 4 (32 papers whose quotes were matched against text the
extractor no longer produces, 12 with no text at all): re-extract those *after*
this ships, so stamps that move do so visibly.

### F2. The map report
One row per map, computed on read from a view, **not stored** — a stored quality
figure that survives a curatorial edit is a lie with a timestamp. The app and a
CLI command select from the same view, so the two cannot disagree.

Reports: verified fraction of definitions and edges; distinct quote strings
against edge count; share of edges on node pairs carrying contradictory types;
largest node's share of edges; singleton share; citation pairs discarded and
why; corpus year distribution and median; run cost and wall clock.

**No thresholds.** With two maps there is no distribution to set one against,
and this project has paid four times for a threshold moved because a rate looked
wrong. Numbers are published with the two known maps beside them as the only
reference points, labelled n=2. A threshold gets set when there are enough maps
to take a quantile from, against a stated distribution, with the resulting rate
named in the commit that sets it.

This is not an eval harness and needs no golden set. Every number comes from the
map's own rows. "Is this map right" needs ground truth and stays out.

### F3. Remove Stage D's same-cluster discard
`pipeline/stage_d_edges.py:145` drops any citation pair whose two papers landed
in the same cluster. Measured: **176 of 479 pairs, 36.7% of the evidence,
deleted by a clustering decision, silently.** 41.5% of those sit inside the
46-paper node backlog item 21 says is mislabelled. Edges with both ends inside
the largest node: **0 of 305, and 0 of 287** — by construction.

The comment defending it is accurate and now argues for the wrong thing. It
dates from when the map was drawn node-to-node; the front door draws papers
individually, and on a paper-level map a within-cluster citation is exactly as
informative as a cross-cluster one.

Removing it recovers the evidence, breaks the coupling by which a clustering
error destroys edges, and makes the hub node harmless. **Raises the recurring
cost of every future map by roughly 37% of Stage D**, about +$0.25 to +$0.60.
The only change here that raises unit cost, and it buys back a third of the
evidence.

### F4. Versioned maps
Today one map exists per concept name, forever. The second person to request
`attention` is refused, and the first map can never be re-run because
re-clustering would overwrite it. Correct under a curated collection, which is
why it appears in none of the backlog items. Under a platform it means **the
generator can generate each thing exactly once, which is not a generator.**

A genealogy row becomes the unit of identity, Stage C keyed by genealogy id
rather than concept plus prompt version, so a re-trace creates a new map beside
the old one. Deletion becomes scoped to the map's requester.

The largest item here, roughly a week, and the thing that separates two showcase
maps from a platform. Prerequisite for F5, for a second requester, and for
validating F3 by running the same concept twice.

### F5. Corpus recency
Median corpus year is **2017**; 7 of 304 papers are 2022 or later; `attention`
stops at **2021**. Anyone asking about a term that matters now gets a map that
ends before it existed. The cause is structural: ranking by citation count is
backward-looking, because recent papers have not been cited yet.

Measured, not guessed: put the corpus year distribution in the map report first,
then set a recency floor against what OpenAlex actually offers for that concept
and field. At $2 to $4 a map, four selection variants cost an afternoon.

### F6. A requester can see the state of their own request
Not email — sending to a stranger needs a verified domain that a Vercel
subdomain cannot be. Showing a signed-in visitor their own requests needs no
domain and is an hour's work. Without it, someone who asks for a map has no way
to learn it exists.

---

## Quality-of-life enhancements

**Q1. Parallelise Stages B and D** (backlog 24). About 143 extractions and 305
classifications run one at a time; most of a trace is network wait. A pool of
eight takes Stage B from ~10 minutes to 1–2, which is most of the gap between
the measured 23.3 and 18.3 minutes and the public "about fifteen". **Must land
after the run-level spend cap**, because parallel workers overshoot a cap
checked between sequential calls.

**Q2. A preview before a run.** Already promised publicly. A free OpenAlex
pre-flight showing the candidate corpus, its year span and an estimated cost
before anyone spends. Becomes load-bearing if requester-pays ever arrives
(decision 26).

**Q3. Show the reproducibility facts.** `prompt_version` and `definitions.model`
are stored and rendered nowhere, so the reproducibility claim on `/about` is true
of the database and false of the interface.

**Q4. Print confidence at the resolution it has.** Two decimal places on a value
taking two distinct values across 53% of edges is false precision, on a page
where `/about` argues against exactly that for other metrics.

**Q5.** Node labels ask for the common thread rather than a name (backlog 21),
and render as provisional until curated. **Q6.** Proper 403s instead of
fail-closed 500s. **Q7.** A marker at the timeline's horizon saying the story
starts in 2011 because arXiv does, not because the idea does (backlog 22).
**Q8.** Corroboration counts (backlog 26), worth more after F3.

---

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
- **Non-arXiv sources**, this month. On `CLAUDE.md`'s OUT list and simultaneously
  on the public roadmap as "working on next" — a contradiction that must be
  resolved in one direction before any code is written.

---

## Open questions

1. **Who pays for a trace.** *Answered: the owner, until the product earns
   organic usage — decision 26.*
2. **Does the OUT list still forbid non-arXiv sources?** `CLAUDE.md` says yes and
   the public roadmap page promises it as next. One of them is wrong today, and
   both readers and agents act on both.
3. **Is a stranger's map public by default?** Decides whether migration 015
   carries a visibility column, and whether request notes and sense glosses are
   ever readable by anyone but their author. Default if unanswered: public, with
   the requester's identity and note never rendered.
4. **Does product rule 3's "users can curate" apply to the requester, or only to
   the owner?** On the platform the person who generated a map cannot touch it.
   Rule 3 is currently satisfied only under a reading where "users" means "the
   owner", and it is marked non-negotiable.
5. **Is "about fifteen minutes" a promise or a description?** Measured runs are
   23.3 and 18.3. If a promise, Q1 moves into Phase 1.
