# Contributing a proposal

## Choose the appropriate starting point

Use an idea issue for a problem or a rough direction. Use an RFC when the change needs a durable design: new syntax or semantics, a public API, an architectural boundary, compatibility policy, or a significant tooling workflow. Small bug fixes do not need an RFC merely to repair documented behavior.

Search the index, open proposal PRs, and relevant GTI plans/ADRs first. An existing restriction is context to evaluate, not an automatic veto. Explain explicitly when a proposal revises a prior decision.

## Draft and publish

1. Create a branch such as `proposal/macros` (Codex contributors use `codex/proposal-macros`).
2. Run `python3 scripts/rfcs.py new <slug> --title "Feature name" --author "@handle" --area language`. Areas are `language`, `stdlib`, `compiler`, `tooling`, and `process`.
3. Develop the generated RFC. Use examples to make the proposed behavior concrete. Separate current implementation facts, proposed semantics, unresolved questions, and measured results.
4. Run `python3 scripts/rfcs.py index` and `python3 scripts/rfcs.py check`, then commit and open a draft PR.
5. Set the RFC's `Proposal` field to that PR's URL. Update the `Updated` date and regenerate the index whenever the proposal changes.
6. When ready for discussion, set the document's status to `review` and mark the PR ready. A maintainer can merge a draft or reviewed document into the catalog without approving the feature itself.

The generator's number is provisional until merge. If another proposal takes that number first, rename your file and heading to the next unused number and regenerate the index. Never reuse or renumber a merged RFC, including one that was rejected or withdrawn. Avoid changing a merged filename merely to retitle a proposal.

Keep the template's metadata and section headings. A draft can explicitly say that a question is unresolved. If a section does not apply, give a short reason. Do not invent measurements, approvals, authors, implementation status, or compatibility guarantees to fill a template.

## Review and decisions

Review should examine the user-facing benefit, general semantics, ownership and lifetime rules, implementation boundaries, compatibility, diagnostics/tooling, runtime costs, and validation criteria. GTI semantics are authoritative; resemblance to C++ and emitted code are not specifications. LLVM is the primary development backend. Do not make C++ feature parity a prerequisite for a new feature.

A status change to `accepted` requires an explicit decision from the project owner or a delegated design maintainer. Link the decision comment or review in `Decision`, and summarize who decided, when, why, and any conditions in **Decision record**. A merged PR, green document checks, silence, or an assistant's recommendation is not approval. The owner can record an approval given elsewhere in the PR discussion so the durable record is reviewable.

For `rejected`, `deferred`, or `withdrawn`, retain the document and explain the outcome in the decision record. Rejected proposals also require a decision link. Reconsider a deferred proposal through a PR; an accepted proposal's material semantic change needs explicit renewed approval or a replacement RFC.

For a replacement, use `Supersedes` and `Superseded by` to reference RFC numbers, retain both documents, and record the decision. Do not silently overwrite the older contract.

## Implementation and follow-up

Acceptance authorizes the design, not a claim that it has shipped. Link implementation issues and PRs in `Implementation`; keep the RFC `accepted` while any accepted scope remains incomplete. Mark it `implemented` only when the accepted scope has landed and the referenced implementation records its required validation. Record any deliberate scope revision with an owner decision rather than declaring unfinished work complete.

Implementation changes use the lifecycle and CI of their own repository. This repository's document checks are not implementation, safety, performance, preview, nightly, beta, or stable validation. Update canonical specifications and examples with the implementation, and link those documents from the RFC. Track release availability in the implementation repository.

## Document checks

```sh
python3 scripts/rfcs.py index
python3 scripts/rfcs.py check
python3 -m unittest discover -s tests -v
```

The checker validates unique IDs, known statuses/areas, dates, required sections, decision/implementation references where needed, related RFC IDs, local file links, and the generated index. It does not verify the truth of a design claim or the authority/content of an external decision link; reviewers must do that. Keep the checks fast and independent of compiler builds.
