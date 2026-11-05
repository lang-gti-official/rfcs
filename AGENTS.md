# Working in GTI RFCs

This repository stores design proposals, not compiler implementations. Read README.md and CONTRIBUTING.md before drafting or reviewing an RFC.

- Inspect `git status --short` and preserve unrelated work. Use a dedicated branch; do not change the compiler repository as a side effect of writing a proposal.
- A request to plan or store a feature produces a `draft` proposal, not an accepted feature. Use the template and generator. Publish through a proposal PR when publication is authorized; do not infer acceptance or permission to implement from a planning request.
- Search existing RFCs and relevant GTI specifications, architecture documents, plans, ADRs, and issues. Link historical decisions rather than copying or erasing them. Verify implementation claims against source and tests.
- State current behavior, proposed behavior, alternatives, costs, prerequisites, open questions, and acceptance criteria separately. A macros example in the README is not a pre-approved macro design.
- Preserve GTI's phase authority and ownership/safety requirements. Prefer general capabilities over library-specific exceptions. Design new backend capabilities for LLVM first; C++ is deprecated and receives compatibility bug fixes only through v1.0.
- Consider runtime performance, allocations, code size, compile time, memory, diagnostics, editor tooling, and migration as relevant. Do not invent performance numbers or promise that a proposed capability already works.
- Keep stable IDs, metadata, backlinks, decision records, and the generated index consistent. A draft may record unresolved questions explicitly. Do not create fake RFCs just to populate the index.
- Never mark a proposal accepted without an explicit owner/delegated-maintainer decision. Link its durable record. Merging a draft into the catalog only stores the document. Mark implemented only with evidence that the accepted scope has landed and been validated.
- Run `python3 scripts/rfcs.py check` and `python3 -m unittest discover -s tests -v` for repository tooling changes. Document-only work needs the document check; do not run compiler CI. Regenerate the index with `python3 scripts/rfcs.py index` when needed.
- Use PRs for updates after repository bootstrap. Preserve rejected, withdrawn, deferred, and superseded proposals. Report proposal status and implementation/release status accurately.
