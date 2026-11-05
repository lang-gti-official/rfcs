# GTI RFCs and feature proposals

This is the design workspace for [GTI](https://github.com/lang-gti-official/gti): language features, standard-library APIs, compiler architecture, tools, and project-wide changes.

**[Browse the proposal index](rfcs/README.md)** · **[Propose an idea](https://github.com/lang-gti-official/rfcs/issues/new?template=idea.md)** · **[Open proposal PRs](https://github.com/lang-gti-official/rfcs/pulls)**

An RFC is a *request for comments*. It records a problem, a proposed solution, alternatives, tradeoffs, and the evidence needed to implement it. A proposal can be saved here before the language design is decided.

## Start a proposal

1. Read [CONTRIBUTING.md](CONTRIBUTING.md) and check the index and open PRs for related work.
2. Create a branch, then generate a draft (Python 3.10 or newer):

   ```sh
   python3 scripts/rfcs.py new macros --title "Macros" --author "@your-github-handle" --area language
   ```

3. Fill in the generated file under `rfcs/`. The [template](templates/feature.md) covers semantics, LLVM implementation, safety, performance, tooling, and validation.
4. Update and check the index, commit the files, and open a draft pull request:

   ```sh
   python3 scripts/rfcs.py index
   python3 scripts/rfcs.py check
   ```

The macros command is an example of starting a draft, not a proposed or accepted macro design. The generator assigns the next available RFC number. RFC numbers and GitHub PR numbers are independent; resolve number collisions before merging and keep merged numbers permanent.

## What the statuses mean

| Status | Meaning |
| --- | --- |
| `draft` | A design is being developed; major questions may remain. |
| `review` | Ready for design discussion and an owner decision. |
| `accepted` | The owner or delegated design maintainer approved the recorded design. Implementation may not exist yet. |
| `implemented` | The accepted scope has landed; implementation and validation evidence are linked. This does not by itself mean a toolchain release contains it. |
| `deferred` | Retained for later, with prerequisites or a reason for waiting. |
| `rejected` | Considered and declined, with the rationale retained. |
| `withdrawn` | Withdrawn by its author; retained for context. |
| `superseded` | Replaced by another numbered RFC. |

**Merging a proposal into this repository records it; merging alone never accepts a language feature.** Draft and review proposals can be merged into the catalog so they have a stable home. Acceptance requires an explicit owner/delegated-maintainer decision, a decision link, and an update to the RFC's decision record. No bot automatically accepts or implements an RFC.

## Repository boundaries

- New feature proposals and design discussion belong here.
- Implemented language semantics, architecture, runnable examples, and compiler tests remain in [the GTI repository](https://github.com/lang-gti-official/gti).
- Implementation work is tracked in the relevant implementation repository and linked back to its RFC. Release availability is tracked separately from design approval.
- Existing plans and ADRs stay at their original locations. Link them when relevant; do not copy or silently supersede them. Execution roadmaps can remain alongside the implementation.
- Compiler bugs belong in [GTI issues](https://github.com/lang-gti-official/gti/issues), rather than being treated as new language proposals.

The checks in this repository validate documents only. They do not build the compiler or wait for GTI's compiler CI. Contributions are under the [MIT license](LICENSE).
