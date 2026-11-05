# RFC {{number}}: {{title}}

| Field | Value |
| --- | --- |
| Status | draft |
| Authors | {{author}} |
| Created | {{date}} |
| Updated | {{date}} |
| Area | {{area}} |
| Proposal | pending |
| Decision | pending |
| Implementation | none |
| Supersedes | none |
| Superseded by | none |

## Summary

Describe the proposed feature and its user-visible outcome in a few sentences. This is a draft, not an implementation claim.

## Motivation and goals

Name the programs, APIs, or workflows this enables. Explain the current limitation and how success will be recognized. Link evidence and related designs.

## Non-goals

State deliberate boundaries and work that belongs in a separate proposal.

## Guide-level design

Explain how a GTI user would use the feature, with concrete proposed syntax/API examples. Distinguish examples that work today from examples that require this proposal. Include important failure cases, not only the happy path.

## Semantic rules

Define the language or API contract independently of a particular library client or backend. Address types, evaluation order, ownership, borrowing, lifetime, cleanup, errors, and interaction with existing features where applicable. List unsupported shapes and the reason for each boundary.

## Compiler and tooling design

Identify the owning phases and preserved facts across syntax, semantics, HIR, MIR, LLVM, runtime, and driver boundaries. Include diagnostics, source locations, formatting, LSP/editor behavior, and debugging where affected. LLVM is the primary development backend; do not propose C++ feature parity as an acceptance gate. For a non-compiler proposal, explain the applicable implementation boundaries instead.

## Compatibility and migration

Describe compatibility, defaults, feature discovery, versioning, and migration. Name any prior RFC, specification, or ADR that changes and explain the revision.

## Safety and correctness

State invariants, safe guarantees, explicit unsafe obligations, rejection behavior, and resource/failure boundaries. Explain how these will be proved or tested; do not use a successful demonstration as proof of a general guarantee.

## Performance and resource costs

Describe expected runtime work, allocations, code size, compile time, and memory use where relevant. Identify representative workloads and comparisons needed for acceptance. Separate estimates from measurements and retain required safety checks.

## Alternatives and tradeoffs

Compare credible alternatives, including keeping the current behavior. Explain the tradeoff the owner would accept by choosing this design.

## Unresolved questions

List open design questions and prerequisites. Before acceptance, distinguish resolved core rules from deliberately deferred follow-up work.

## Implementation plan

Describe coherent slices, affected repositories/components, dependencies, and implementation tracking links. Do not promise a release date or mark an unimplemented slice complete.

## Validation and release criteria

Name positive and negative cases, runtime execution/cleanup checks, relevant tooling/platform coverage, performance acceptance, examples, and canonical documentation updates. Compiler and release validation follow the implementation repository's current policy. Document checks here cannot establish implementation or release readiness.

## Decision record

No design decision yet. Record explicit owner/delegated-maintainer decisions with dates, decision-maker, rationale, conditions, and durable links. Preserve changed decisions rather than erasing their history.

## References

Link related RFCs, specifications, architecture documents, ADRs, issues, implementation PRs, and external research. State what each reference contributes.
