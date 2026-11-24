# RFC 0013: Compiler bug-finding coverage for current GTI

| Field | Value |
| --- | --- |
| Status | draft |
| Authors | @gti-language-official (with Claude) |
| Created | 2026-11-24 |
| Updated | 2026-11-24 |
| Area | tooling |
| Proposal | https://github.com/lang-gti-official/rfcs/pull/14 |
| Decision | pending |
| Implementation | none |
| Supersedes | none |
| Superseded by | none |

## Summary

Extend GTI's opt-in compiler bug-finding tools so they exercise the language
as it exists today, not as it existed in October 2026. The tools are the
combination and wrong-code matrices, the feature-interaction campaign and the
libFuzzer harnesses. The proposal has three parts:

1. **Feature breadth.** Add generators for language features that landed after
   the tools were written and that no generator reaches today, for example
   weak ownership, thread-local owners, deferred statements, `if case`, `?`
   propagation, modules and macros.
2. **New oracles that need no second backend.** Now that the C++ backend is
   frozen, every oracle must come from GTI itself: a program's own checks,
   agreement between optimization levels, agreement between compile-time and
   run-time evaluation, and agreement between equivalent source forms.
3. **Coverage-directed targeting and a measured result.** Choose the next
   generators from source-coverage data, and report how much compiler source
   each tool reaches beyond the test suite.

This is a draft campaign proposal. It changes no language rule and claims no
finding beyond those cited.

## Motivation and goals

The phase-one refactor (GTI PRs #673, #676 and #679) made the
tools LLVM-first. It did not widen what they generate. Their generators still
reflect the language of their authorship:

- The 26 wrong-code matrix modules and ten classification matrices cover
  ownership transfer, containers, hierarchies, payload enums, callables,
  destruction order, generics, ranges, threads and RAII. A text search of
  their generators finds no use of `weak_ptr`, `thread_local`, `export`,
  reflection, macros, deferred statements, `if case`, `consteval`, `?`
  propagation, allocators or panics.
- The feature-interaction campaign has eleven factors (generic, lambda,
  expected, move-only, payload enum, vector, read-only borrow, propagation,
  visible cleanup, nested call, control flow). Its phase-one report lists the
  uncovered axes: dynamic dispatch, mutable and stored borrows, strings and
  formatting, containers other than `std::vector`, range-for, constexpr,
  panics, the concurrent execution profile, native interop and multi-file
  programs.
- Since 0.484, GTI has added first-class modules (0.493.0), source-defined
  shared and weak ownership (0.491.0), thread-local owners (0.493.2), explicit
  default construction (0.488.0), associated type families, reflected method
  dispatch, typed and procedural macros, and lifetime parameters. Changelog
  fragments not yet released add borrowed container elements, owner-tied
  elements, owning-enum arrays, closures and packs, `if case` payload binding,
  switch-case actions, init statements, range structured bindings, receiver
  captures, borrowed iterator yields, `?` error conversion and wider constexpr
  (range-for, owned text, erased and static borrows).

Phase one showed that cheap combination sweeps still find real defects in
current code. The level-divergence check added in #676 found GTI #677 on its
first run: `r = (r, 2);` into a dead local builds at O0 and fails MIR
verification at O1 and above. Nothing else reached that shape, because the
suite runs per commit at O0.

The committed source-coverage baseline (`tests/coverage_baseline.json`,
`8d4ed461`, 89.29% lines) shows where the suite is thinnest in compiler
phases that generated programs can reach. Among files of 800 lines or more:

| File | Line coverage | Uncovered lines |
| --- | --- | --- |
| `src/compiler/mir_constant_evaluator.cpp` | 83.1% | 552 |
| `src/compiler/mir_optimization_verifier.cpp` | 86.0% | 130 |
| `src/compiler/semantic_body_analysis.cpp` | 86.0% | 2178 |
| `src/compiler/semantic_ownership_analysis.cpp` | 86.2% | 1935 |
| `src/compiler/semantic_type_resolution.cpp` | 87.5% | 1033 |
| `src/compiler/semantic_macro.cpp` | 87.5% | 168 |
| `src/compiler/mir_program_verifier.cpp` | 91.4% | 1879 |
| `src/compiler/mir_body_lowering.cpp` | 91.2% | 1483 |

The driver files (`build.cpp` at 64.4%, `manifest.cpp`, `project.cpp`) are
thinner still, but they need project-level tools, not program generators. They
are out of scope here (see Non-goals).

Success means three things:

- Every language feature that has shipped, or has a merged changelog fragment
  as of acceptance, is reached by at least one generator, or is listed as
  deliberately excluded with a reason.
- Each new oracle has a negative control showing it detects the defect class
  it claims to.
- A measured report shows each tool's coverage beyond the per-commit suite,
  for the files above.

## Non-goals

- **No new merge gate, no scheduled run and no per-commit cost.** The tools
  stay local and opt-in, as the owner decided (see Decision record).
- **No C++ oracle or parity.** The C++ backend is frozen. It is not used to
  judge GTI semantics, and C++ parity is not an acceptance criterion.
- **No formal verification.** RFC 0002 owns machine-checked borrow-checker
  soundness. This proposal produces bug-finding evidence, not proofs.
- **No driver, package or LSP generators.** Project builds, manifests and the
  editor protocol deserve their own proposal. This one covers programs.
- **No compiler fixes.** Findings become issues with minimal reproducers and
  regressions in the owning suite through the normal compiler workflow.
- **No arbitrary whole-language source generator.** Each generator stays a
  bounded grammar of supported shapes with an independent expectation. Wider
  random exploration stays with the libFuzzer harnesses.

## Guide-level design

A developer chasing a defect class, or reviewing a release, runs the
generators that reach it. The commands below are proposed. Today only the
existing matrices, `--levels`, `--json` and `--baseline` work as shown.

```sh
# Proposed new wrong-code modules beside the existing 26
tests/coverage/matrices/llvm_wrongcode_matrix.py build-release/gti \
    --matrix weak_owners thread_local_owners deferred propagation \
    --levels O0,O2,O3 --json new.json --baseline main.json

# Proposed oracle: compile-time and run-time evaluation of the same function agree
tests/coverage/matrices/constexpr_equivalence_matrix.py build-release/gti

# Proposed oracle: a program split across modules behaves like the single file
tests/coverage/matrices/module_split_matrix.py build-release/gti

# Proposed new factors in the interaction campaign
python3 scripts/debug/feature_interactions.py run --gti build-release/gti \
    --factors default,dispatch,text,map,range_for,panic --strength 2
```

A failing cell or case keeps its source and its per-level verdicts. It feeds
the existing capture, reduce and replay pipeline
(`scripts/debug/capture_compiler_failure.py`, `reduce_compiler_failure.py`).
That pipeline produces the minimal reproducer for an issue. A finding is
recorded in `tests/coverage/FINDINGS.md` and in the issue, never as an
exclusion in the generator.

## Semantic rules

This proposal defines tooling contracts, not language semantics. Expected
results come only from documented GTI semantics: `docs/language/`, and in
particular `execution.md` for evaluation and destruction order. They never
come from what a backend happens to emit.

### Oracles

Each oracle states what it can prove and what it cannot.

1. **Self-checking programs** (existing). A cell computes its expected values
   from its literal inputs and counts tracked destructions and their order. A
   mismatch is wrong code. It cannot catch a defect that corrupts the check
   itself identically.
2. **Level agreement** (added in phase one). A cell built at several LLVM
   levels must reach the same verdict at each. Disagreement is a defect at
   some level. The verdict does not say which level is wrong.
3. **Compile-time and run-time agreement** (proposed). A function evaluated
   in a constant context (a `constexpr` initializer or `static_assert`) and
   the same function called at run time must produce the same value or the
   same defined failure. Where the language allows a difference, for example
   limits that only exist at compile time, the generator checks that
   documented rule rather than equality. This oracle targets the MIR constant
   evaluator, following the `L-CONST-01` direction of growing `constexpr`
   toward MIR execution.
4. **Equivalent source forms** (proposed, extending the campaign's renamed
   variant). Transformations that must not change meaning:
   - Splitting declarations across exported modules.
   - Replacing a typed-macro invocation with its hand-written expansion.
   - Moving a local into an `if (init; cond)` init statement.
   - Replacing an explicit match with `if case`.
   - Replacing a manual early return with `?`.

   A transformation is admitted only where `docs/language/` says the two forms
   are equivalent. Where it says they differ (for example in destruction
   timing), the generator checks the documented difference.
5. **Invalid siblings** (existing pattern). For every accepted ownership or
   borrow shape, a near-identical program the rules forbid must be rejected
   with the documented diagnostic family. This catches soundness gaps in the
   other direction, where a bad program is wrongly accepted.

### Admission of new axes

A new generator axis needs all of the following:

- a documented contract to check against
- at least one hand-checked cell per axis value, which may be negative
- a negative control: a deliberately broken variant the oracle must flag
- an explicit list of excluded shapes, each with a reason (an unimplemented
  feature, or a documented restriction)

Compiler defects found while building a generator are findings. They never
become exclusions.

## Compiler and tooling design

No compiler phase changes. The tooling changes are:

- **Matrices** (`tests/coverage/matrices/`).
  - New `llvm_wrongcode/` modules, one per axis family. Candidates in
    proposed priority order:
    - `weak_owners` (shared and weak ownership: expiry, cycles, cleanup order)
    - `thread_local_owners`
    - `deferred` (deferred statements under early exit, loops and failure)
    - `propagation` (`?` and error conversion through owners and cleanup)
    - `payload_binding` (`if case`, switch-case actions, init statements,
      range structured bindings)
    - `owning_enum_transport` (enum arrays, closures and packs)
    - `borrowed_elements` (borrowed container elements, owner-tied elements,
      borrowed iterator yields)
    - `lifetimes` (functions with lifetime parameters, plus their invalid
      siblings)
    - `conversions` (user-defined conversions, explicit default construction,
      protocol concepts)
    - `allocation` (allocator-backed owners and storage leases)
    - `panics` (defined failure: cleanup and exit status)
  - New stand-alone oracle matrices: `constexpr_equivalence_matrix.py`,
    `module_split_matrix.py` and `macro_expansion_matrix.py`. All use
    `matrix_support.py`.
  - Optional `-g` agreement: the same cell with and without debug info must
    reach the same verdict. This is cheap, and debug-info emission is a
    distinct LLVM path.
- **Feature-interaction campaign** (`scripts/debug/feature_interaction_model.py`).
  - Add factors in two tranches, each tranche keeping the strength-2 run
    within a stated budget:
    - Tranche A: `dispatch` (an interface or virtual call in the transport
      path), `text` (string building and formatting of the transported value),
      `map` (a second container family), `range_for`.
    - Tranche B: `mut_borrow` (a mutable borrow or a stored reference), `panic`
      (defined failure at a chosen step), `concurrent` (transport across
      `std::thread` under the concurrent profile), `constexpr` (one stage
      evaluated at compile time).
  - The independent oracle grows with each factor. A factor the oracle cannot
    model independently is not added.
  - Allow `--levels` to select O0–O3, so O1 and O2 regressions (such as #677)
    are reachable without code changes.
- **libFuzzer harnesses** (`fuzz/`). After #679 the pipeline harness runs
  the driver's LLVM path at O0–O3 (selected by the first input byte),
  compares MIR, textual IR and the object across two fresh runs, and
  verifies the re-parsed module. Five-minute exploratory runs from the
  checked-in corpus ran 131k pipeline inputs and 221k source-loader inputs
  cleanly. Their 17-byte parser timeout was first dismissed because the
  replay used `gti check`, which stopped at the missing `gti.toml`; replayed
  as a direct compile it is a real hang (#693). Seeding the pipeline harness
  with the 7,612 single-file `tests/ui` programs and running 45 minutes in
  fork mode found far more: an internal error at O1 and above (#686) and
  parser recovery spins in three entry points, protocol-concept bodies
  (#692), `for` statements (#693) and class member declarations (#696), plus
  compile time that doubles per link in a chain of constructors (#697).
  Under ASan, deep generic instantiation overflows the stack before the
  release compiler's depth limit (GTI-S2105) is reached; those are harness
  artifacts, not defects. The formatter non-idempotence did not reproduce.
  Seeding was the single largest improvement. The limits are now reach and
  triage, not checking:
  - A structure-aware mutator, or grammar-seeded corpus, for the pipeline
    harness, seeded from `tests/ui`, `examples/` and the coverage corpus, so
    that more inputs pass semantics and reach MIR and LLVM.
  - A corpus-refresh routine that merges inputs which raise coverage into the
    curated seed corpus deliberately.
  - A reproduction step for harness timeouts and non-idempotence, so that
    flaky reports are either confirmed and captured or discarded. It replays
    with a direct compile (never `gti check`, which needs a project), on the
    release compiler, and clusters hangs by sampled stack before reducing.
  - Restoring ASan container-overflow detection in the pipeline harness (it
    is off there because uninstrumented LLVM libraries share vectors with
    instrumented GTI passes), for example by building LLVM instrumented or
    by suppressing only frames inside LLVM.
- **Coverage measurement.** Add a mode that runs a chosen tool under the
  existing `-DGTI_ENABLE_SOURCE_COVERAGE=ON` build. It reports the lines and
  branches the tool reaches that the per-commit suite does not, using
  `scripts/coverage_report.py` and the committed baseline format. This
  measures each generator's marginal value and selects the next target.
- **Findings flow.** Matrices and the campaign write a capture bundle for each
  hard verdict on request (`--capture`), so reduction needs no manual setup.

## Compatibility and migration

- Existing matrix command lines, verdicts and the `--json` schema stay
  compatible. New verdicts or fields extend schema 1. A breaking change bumps
  the schema and keeps `--baseline` able to read the old one.
- Interaction-campaign records keep schema `gti-feature-interaction-failure-v1`.
  New factors default to off when an older record is replayed, as the
  version-one control-flow migration already does.
- No language, compiler, CLI or packaging change. Nothing is user-visible to
  GTI programmers.

## Safety and correctness

- Generators only claim the oracle they implement. A clean matrix is evidence
  that a bounded shape family behaves as checked. It is not a proof for the
  feature.
- Every new axis carries a negative control. The existing
  `scripts/debug/selftest.py` pattern is extended so that each new oracle has
  a check that it still detects its defect class.
- Resource safety while running the tools is enforced as it is today:
  watchdogs, process-group kills, private work directories, and libFuzzer's
  `-rss_limit_mb` and `-malloc_limit_mb`. Shapes known to exhaust memory
  (S13, F19) stay behind explicit opt-in flags.
- Generated programs are compiled and run only from new temporary directories,
  never from the repository.

## Performance and resource costs

- No per-commit or compiler run-time cost.
- **Local run time** grows roughly with the number of cells times the number
  of levels. Phase one measured the existing wrong-code matrix at 864 cells,
  O0 and O2, with six jobs in one suite slot on macOS arm64. Its wall time was
  not recorded and should be measured before setting budgets. Each new module
  states its cell count, and a default run of all matrices should finish
  within one suite slot of an agreed length (open question).
- **Interaction campaign.** Each added factor grows the strength-2 covering
  array. Each tranche records cases, native outcomes and wall time at seed
  20261003 before and after.
- **Coverage runs** use the instrumented build, which already takes about an
  hour per shard in `suite-measures.yml`. Per-tool runs are local and opt-in.

## Alternatives and tradeoffs

- **Keep the generators as they are.** Zero cost, but most features added
  since 0.484 go unreached, and the tools' clean results become less
  meaningful as the language grows.
- **Rely on libFuzzer alone.** Coverage-guided mutation is broad but rarely
  forms valid ownership-heavy programs, and it has no semantic oracle beyond
  crashes and its pipeline properties. Wrong code needs the self-checking and
  equivalence oracles.
- **Add the cases as `tests/ui` regressions instead.** Regressions pin known
  shapes cheaply per commit. Sweeping the product of two axes at several
  levels is what finds the unknown cell, and that cost belongs off the
  per-commit path. Each finding still lands as a regression.
- **Use the C++ backend as an oracle again.** Rejected. It is frozen, it has
  known defects of its own (lifecycle dispatch), and it would make GTI
  semantics depend on emitted C++.

## Unresolved questions

1. **Automation (settled 2026-11-24: local only).** The owner chose to keep
   every tool local and opt-in, with no scheduled or CI run. This matches the
   earlier instruction to keep the borrow laboratory off CI and the
   hosted-runner cost guardrail. Revisiting it needs a new owner decision.
2. **Budget.** What wall-time budget should a default "all matrices" run and
   each campaign tranche meet?
3. **Priority.** Is the proposed priority order of new modules right? It
   follows recency and the coverage data, not measured defect density.
4. **Constant-evaluation equivalence.** For which operations does the
   language intend compile-time and run-time results to differ (resource
   limits, allocation, I/O)? The oracle needs that list from `docs/language/`
   before it can be implemented.
5. **Fuzzing scope.** Is a structure-aware mutator worth its maintenance,
   or is a grammar-seeded corpus enough to move inputs past semantics?
6. **Unmerged features.** Should features that exist only as RFC drafts
   (lifetime parameters' inference, borrowed container elements under
   RFC 0003, RFC 0010 streams) be generated only after their implementation
   merges? This draft assumes yes.

## Implementation plan

The slices are independent unless noted. Each is one GTI PR through the
normal workflow.

1. **Coverage baseline for the tools.** Add the per-tool coverage mode and
   record each existing tool's marginal coverage. This sets the "before"
   numbers for every later slice.
2. **Wrong-code modules, tranche 1:** `weak_owners`, `thread_local_owners`,
   `deferred`, `propagation`, `panics`.
3. **Wrong-code modules, tranche 2:** `payload_binding`,
   `owning_enum_transport`, `borrowed_elements`, `conversions`, `allocation`,
   `lifetimes`.
4. **Oracle matrices:** `constexpr_equivalence_matrix.py` (after question 4
   is resolved), `module_split_matrix.py`, `macro_expansion_matrix.py`, and
   `-g` agreement.
5. **Interaction campaign, tranche A**, plus `--levels`.
6. **Interaction campaign, tranche B.**
7. **Fuzz items:** seeded corpus, refresh, timeout reproduction.
8. **Findings flow:** `--capture` bundles from matrices and the campaign.

Each slice runs its tools on current `main` and files any findings as issues
with reduced reproducers.

## Validation and release criteria

For each slice:

- **Negative controls.** Every new oracle and axis has at least one injected
  defect it must report, checked by the self-test, and a hand-checked positive
  cell per axis value.
- **A real run.** A full run on current `main` (macOS arm64; Linux x86_64 for
  any slice that touches platform behavior), with cell counts, verdict
  distribution and wall time recorded in `tests/coverage/matrices/README.md`
  or `docs/architecture/verification.md`.
- **Marginal coverage.** For slice 2 onward, the tool's added coverage on the
  files in Motivation, measured with slice 1's mode. A slice that adds no
  coverage and finds nothing records that, and its axis can be dropped.
- **Findings** are filed and cross-referenced in `tests/coverage/FINDINGS.md`.
  None is converted into an exclusion.
- **Tooling tests.** The tooling's existing registered tests
  (`feature_interaction_model`, `feature_interaction_smoke`,
  `compiler_debug_tooling`, `fuzzer_smoke`) keep passing. New registered tests
  follow GTI's test-freeze rule: `gti-test` cases or `tests/unit`, not new
  old-style harnesses.

The campaign is complete when every listed feature is reached or deliberately
excluded, and the coverage report exists for every tool.

## Decision record

No decision on the design as a whole; the status stays `draft`.

- 2026-11-24, project owner, in the planning conversation that produced this
  draft: the tools stay local and opt-in, with no scheduled or CI run
  (Unresolved question 1). Recorded on the proposal PR.

## References

- [RFC 0002](0002-borrow-checker-verification.md): borrow-checker verification.
  It owns the formal-verification track, and its laboratory is the precedent
  for keeping bug-finding tools opt-in.
- [RFC 0003](0003-borrowed-container-elements.md): borrowed container
  elements, one of the features to be generated.
- GTI `docs/architecture/verification.md`: "Suite yardsticks" for the source
  coverage and seeded-bug measures, and "Failure Capture And Opt-In Fuzzing"
  for the interaction campaign, the capture and reduce pipeline, and the
  libFuzzer harnesses.
- GTI `tests/coverage/matrices/README.md`: the matrices, the shared runner
  and the phase-one results.
- GTI `tests/coverage/FINDINGS.md`: defects found by the coverage corpus and
  matrices.
- GTI `docs/plans/archive/compiler-bug-finding-and-triage.md`: the completed
  `Q-FUZZ-01` plan that built the capture, reduce and fuzz facilities.
- GTI issue #677: the O1+ ICE found by the phase-one level-agreement check.
- GTI `docs/language/execution.md`: evaluation, cleanup and dispatch order,
  the source of expected results.
- GTI `AGENTS.md`, "Constexpr Evolution" (`L-CONST-01`): the direction the
  constant-evaluation oracle follows.
