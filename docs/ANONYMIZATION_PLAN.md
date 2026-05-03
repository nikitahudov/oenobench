# Double-blind anonymization plan (run-immediately-before-submission)

**When to execute**: only at the very end, immediately before the OpenReview
paper submission (deadline 2026-05-06 AoE). All preceding work — Phase 5
evaluation, paper drafting, datasheet, etc. — proceeds under real identity
(`nikitahudov`).

**Why this ordering**: anonymization is fully mechanical, reversible, and
takes ~3-4h. Doing it last avoids working under partial-identity confusion
during the substantive work, and avoids cache-busting reviewers if any
links happen to be inspected pre-submission.

**Reversal after acceptance**: post-acceptance / camera-ready, swap every
anonymous artifact back to the real-identity equivalents. The reverse
mapping is captured below; keep this file updated through that round.

---

## What gets anonymized (artifacts visible to reviewers)

### 1. The paper PDF (and any supplementary PDF)
- **Title page**: remove author names + affiliations
- **Body**:
  - All "we" references that imply specific identity
  - All self-citations to prior author work (replace with `[Anonymous, 2026]`)
  - Acknowledgments section: blank or "Acknowledgments redacted for review"
  - Funding statements: redact
- **Templates**: NeurIPS-provided LaTeX template has an `anonymous` flag —
  use it.

### 2. The HuggingFace dataset
- Current: `https://huggingface.co/datasets/nikitahudov/oenobench-v1`
- **For review**: clone to a new anonymous HF handle, e.g.
  `oenobench-anon-2026` or `anonymous-ed-2026` (need a fresh email +
  separate HF account; create new HF account and re-upload the same
  files under the anonymous namespace)
- **Strip from the dataset**:
  - `README.md` `creator` block, `email`, `Contact / issues` links
  - `croissant.json` `creator` block + GitHub URL references
  - any reference to `nikitahudov/oenobench` in the body
- **Replace with**:
  - generic project URL (anonymous.4open.science mirror — see below)
  - generic contact (e.g., "redacted for double-blind review")

### 3. The GitHub repository
- Current: `https://github.com/nikitahudov/oenobench`
- **For review**: create an `anonymous.4open.science` mirror at
  https://anonymous.4open.science (one-click anon mirror). It accepts a
  GitHub repo URL and serves it back without commit-author / repo-owner
  info. Note: anon.4open.science requires the source repo to be public.
- Limitation: anon.4open.science does NOT hide commit *messages*. If any
  commit message contains author names or affiliations (`Co-Authored-By:
  Claude Opus 4.7 (1M context) <noreply@anthropic.com>` is fine —
  generic), audit + amend if needed.

### 4. Public web traces (search-time leakage)
- This dataset is brand new (May 2026), no academic blog posts to scrub
- The `nikitahudov/oenobench-v1` HF page IS public at submission time but
  reviewers reach the anon mirror via the OpenReview form
- If reviewers Google "OenoBench wine benchmark," they'll find this page
- Mitigation: NeurIPS reviewers are explicitly told not to Google
  submission keywords; this is a known limitation of late-stage
  anonymization, not a process violation

---

## What stays under real identity (not visible to reviewers)

- The OpenReview form's author block (the system holds the real name —
  only reviewers see anonymized PDFs)
- The OpenReview submission form's "co-authors" list (filled with real
  names; ACs/SACs see them, reviewers don't)
- The author email used for OpenReview correspondence
- The local Postgres DB + scraping pipeline
- This `docs/ANONYMIZATION_PLAN.md` file (private to repo)
- All `git log` history on the GitHub repo (note the limitation above on
  anon.4open.science — commit messages survive)

---

## Concrete checklist (run when ready)

```
[ ] 1. Create new HF account (e.g. oenobench-anon-2026)
       Need: a fresh email (e.g. burner Gmail) — DO NOT reuse nikitahudov's
[ ] 2. Re-upload the OenoBench package to <anon-handle>/oenobench-v1
       Use scripts/export_release_v1_2_to_parquet.py + the anonymized
       README.md + croissant.json (see step 4)
[ ] 3. Create anon.4open.science mirror of github.com/nikitahudov/oenobench
       URL: https://anonymous.4open.science/r/oenobench-<hash>/
[ ] 4. Anonymize files (use scripts/anonymize_for_review.py — see below):
       - data/exports/oenobench_v1/README.md
       - data/exports/oenobench_v1/croissant.json
       - docs/huggingface/DATASET_CARD.md
       - docs/huggingface/croissant.json
       - paper.pdf (if not already anonymized via LaTeX flag)
[ ] 5. Re-upload anonymized README + croissant to the new anon HF dataset
[ ] 6. Update OpenReview submission form:
       - dataset_url → <anon-handle>/oenobench-v1 HF URL
       - code_url → anon.4open.science mirror URL
       - paper.pdf → anonymized version
       - select review_mode = "Double-blind"
[ ] 7. Verify:
       - HF anon repo loads via load_dataset() with no auth
       - anon.4open.science mirror is browsable
       - Paper PDF has no author info (grep PDF for known author names)
       - Croissant on anon HF has no creator block
[ ] 8. Take down (or set private) the real-name HF dataset for the review
       window
       - HfApi().update_repo_visibility('nikitahudov/oenobench-v1',
         private=True)
       - This breaks any external link, but the anon mirror serves the
         same data
[ ] 9. Note in a private file (NOT committed to anon repo): the mapping
       between anon handle and real identity, so we can swap back.
```

---

## Reverse plan (run after reviews / acceptance)

```
[ ] 1. Set the real-name HF dataset back to public:
       HfApi().update_repo_visibility('nikitahudov/oenobench-v1',
       private=False)
[ ] 2. Re-upload the un-anonymized README + croissant from
       data/exports/oenobench_v1/ to nikitahudov/oenobench-v1
[ ] 3. (Optional) delete the anonymous HF account / repo, OR leave as
       a redirect for citation continuity
[ ] 4. Submit the camera-ready paper with real author names
[ ] 5. Update CURRENT_STATUS.md / PROCESS_LOG.md noting the
       anonymization round finished
```

---

## Helper script (build now, run later)

`scripts/anonymize_for_review.py` — to be authored on demand. Specs:

- Input: list of files to anonymize (README.md, croissant.json,
  DATASET_CARD.md)
- Operations:
  - Replace `Nikita Hudov` / `nikitahudov` / personal email with
    placeholders
  - Replace GitHub URL `github.com/nikitahudov/oenobench` with the
    anon.4open.science URL
  - Replace HuggingFace URL `huggingface.co/datasets/nikitahudov/oenobench-v1`
    with the new `<anon-handle>/oenobench-v1` URL
  - Replace any contact info / acknowledgments
- Output: writes anonymized copies to `data/exports/oenobench_v1_anon/`
- Idempotent — running it twice produces identical output

The reverse: `scripts/de_anonymize_for_camera_ready.py` flips the
operations using the same mapping.

---

## Pre-flight readiness check (do BEFORE starting anonymization)

- [ ] Phase 5 evaluation completed (16 configs × 3,329 Qs)
- [ ] Paper draft finalised (LaTeX in NeurIPS template with anonymous flag)
- [ ] Datasheet finalised
- [ ] CURRENT_STATUS / PROCESS_LOG updated with all latest results
- [ ] All authoring done; only mechanical scrubbing remains
- [ ] At least 2-3 hours of focused time before the deadline

If any of those is incomplete, FINISH FIRST. The anonymization step is
trivial and mechanical; the substantive work is the bottleneck.
