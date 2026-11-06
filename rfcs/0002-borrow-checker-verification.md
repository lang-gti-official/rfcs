# RFC 0002: Borrow-checker verification in three phases

| Field | Value |
| --- | --- |
| Status | draft |
| Authors | @gti-language-official (with Codex) |
| Created | 2026-11-06 |
| Updated | 2026-11-06 |
| Area | compiler |
| Proposal | pending |
| Decision | pending |
| Implementation | none |
| Supersedes | none |
| Superseded by | none |

## Summary

Build stronger, independently checkable evidence that GTI enforces its ownership
and borrowing guarantees. Deliver exactly three cumulative phases:

1. **Enforcement tests:** a rule-to-evidence inventory, adversarial interaction
   tests, and mutations that demonstrate the checks actually detect violations.
2. **Independent model and generated counterexamples:** a small reference checker
   and memory-execution model, bounded exhaustive exploration, and reproducible
   generated tests compared with the production compiler.
3. **Machine-checked core soundness and compiler correspondence:** prove a
   precisely scoped sequential core and its reference checking algorithm, then
   validate that supported compiler output preserves the modeled obligations.

Each phase has its own useful deliverables and mandatory acceptance gate. Phase 1
must catch enforcement regressions without waiting for a model; phase 2 must
find and minimize disagreements without waiting for a theorem prover; phase 3
must deliver checked proofs and an executable compiler connection, not just a
formalization document. None licenses a claim that the whole GTI compiler or all
unsafe libraries are formally verified.

This is a draft campaign proposal. It changes neither language permissions nor
implementation today. RFC 0001 is provisionally used by the open procedural-macro
proposal; this draft uses 0002 to avoid that collision, subject to merge-time ID
checks.

## Motivation and goals

A borrow checker can reject familiar bad examples yet miss a combination of
returned references, owner movement, conditional paths, cleanup, and generic
instantiation. There are distinct obligations:

- The language rules must prevent the memory errors they promise to prevent.
- The implementation must enforce those rules, including interactions.
- Lowering and optimization must preserve them; native execution must implement
  the resulting program correctly.
- Unsafe implementations behind safe APIs must uphold the contracts the checker
  relies on. Arbitrary unsafe code cannot be made safe by trusting those contracts.

The user outcome is greater justified confidence in ordinary GTI code using
references, containers, iterators, callbacks, temporary arguments, and failure
cleanup. Contributors should obtain small reproducible counterexamples instead
of relying on user reports or test counts as a proxy for soundness.

### Current evidence and limits

The inspected GTI revision is
[`ea499038dfbd68c6b5975c68a2d14319ea1436be`](https://github.com/lang-gti-official/gti/commit/ea499038dfbd68c6b5975c68a2d14319ea1436be),
the published panic-temporary-loan fix branch, not a claim about current main or
nightly inclusion. Source and tests establish existing foundations:

- Semantic analysis owns source borrowing decisions; MIR verifies preserved
  ownership facts and executable control flow. The existing place/state plan
  explicitly records that the layers share an ownership vocabulary and place
  relations. This is defense in depth, not fully independent formal assurance.
- `scalar_temporary_borrow_tests.cpp` already forges escaping loans and incorrect
  cleanup order and requires verification failure. Other ownership tests and
  `verification.md` record carrier/dependency mutation coverage.
- [GTI PR #266](https://github.com/lang-gti-official/gti/pull/266) repaired an
  invocation failure path whose temporary-loan endpoints were ordered incorrectly.
  The verifier rejected it before native code generation. This illustrates a
  caught lowering defect; it does not demonstrate an accepted unsafe program.

These observations are a starting sample, not a completed soundness audit. Phase
1 must inventory current main and existing infrastructure before adding parallel
machinery. Preserve existing plans, ADRs, and evidence; link them rather than
replacing their histories.

## Non-goals

- New borrow permissions, lifetime syntax, a wholesale replacement checker, or
  adopting Rust's rules as GTI semantics.
- Proving all of LLVM, the native runtime, the full language, foreign code, or
  arbitrary unsafe libraries correct in this campaign.
- Implementing a general public debugger/interpreter or a second production
  language engine. The model is a restricted verification tool.
- New C++ backend capability or per-feature C++ differential acceptance. Runtime
  evidence uses shipped LLVM O0/O3; C++ follows its separate repository policy.
- Delaying known safety fixes until all three phases finish. Discovered defects
  follow normal repair and release-blocking policy immediately.

## Guide-level design

No source syntax changes. Contributors gain a maintained evidence entry for each
ownership invariant, regression fixtures, reproducible generation, and precise
reports of what the model or proof covers.

A conceptual test sequence is:

```text
initialize owner O.field
create mutable borrow R of O.field
attempt to destroy O
use R
```

It must be rejected. A nearby positive case ends R before destroying O. Further
cases put the attempted destruction on one branch, inside a called function,
after a move, or on panic cleanup. These are abstract operation examples, not
new GTI syntax. Tests must distinguish a legitimate child reborrow from an
independent conflicting mutable borrow; merely counting live references is not
a correct aliasing rule.

Every report identifies one of: valid and accepted; invalid and rejected;
accepted but modeled violation; conservative rejection; internal compiler error;
unsupported model shape; or timeout/resource limit. Unsupported and timeout do
not count as passes. A compiler rejection alone does not prove safety for cases
it accepts, and a successful execution covers only that execution.

A generated failure record includes compiler/model revisions, schema version,
seed, generation bounds, target/mode, original and reduced program, diagnostics,
execution trace, and the exact command to replay it.

## Semantic rules

This proposal checks GTI's existing contract rather than creating a new source
contract. Freeze a reviewed semantic profile for each model/proof version. If
implementation and specification disagree, resolve the discrepancy explicitly;
do not silently teach the reference model whatever production currently does.

The invariant inventory must include:

| Obligation | Facts to preserve and challenge |
| --- | --- |
| Valid referent | Storage identity, initialization state, allocation/lifetime epoch, and all possible origins |
| Access authority | Shared/mutable permission, overlap, parent reborrow suspension and restoration, conservative may-alias treatment |
| Escape boundary | Temporary, local, argument, returned, and stored-carrier lifetime constraints |
| Ownership transition | Move, replacement, partial initialization, destruction and invalidation of dependent borrows |
| Control flow | Joins, loops, reachable paths, calls, recursion where admitted, normal and failure successors |
| Interprocedural contract | Actual callee behavior agrees with caller-visible origin/access summaries; summaries cannot justify each other circularly |
| Cleanup | Owners remain alive through every dependent use and destructor; loan ends and drops are balanced and correctly ordered |
| Representation preservation | HIR/MIR transport, optimization, and loan erasure retain the required execution behavior |

For phase 2 and the phase 3 theorem, the mandatory initial core is sequential,
monomorphic, first-order code with owned scalar/record storage, statically named
fields, shared/mutable references and reborrows, moves and reinitialization,
conditional control flow and loops, nonrecursive direct calls with checked
reference results, call-only read borrows of temporaries, and explicit normal
and defined-failure cleanup. Include at least one bounded owned-allocation form
with allocation identity and generation, so use-after-free is represented rather
than assumed away. Destruction in the core consists of explicit checked field
cleanup/free operations; arbitrary user destructor bodies are outside the initial
proof unless translated into the admitted operations.

Production tests in phase 1 have wider coverage than that core. Model adapters
must reject unsupported operations explicitly, including unknown call effects.
General dynamic indexing, recursive calls, enums with borrow-carrying variants,
closures/type erasure, retained-owner transitive graphs, arbitrary raw pointers,
FFI, atomics and concurrency are extension obligations, not silently abstracted
as harmless. Phase 1 inventories them; phase 2 retains their production tests;
phase 3 records prerequisites for extending the model and proof. Any narrowing of
the mandatory core requires an explicit scope decision, not a passing exclusion.

## Compiler and tooling design

Use the existing directional architecture:

| Layer | Proposed verification responsibility |
| --- | --- |
| Parser/AST | Preserve syntax and source provenance; generated-source tests also exercise this boundary |
| Semantics | Continue deciding source validity and publishing origin/access/escape facts |
| HIR | Preserve concrete instance identities and selected contracts; export test observations without redefining semantics |
| MIR lowering/verifier | Construct and validate executable loan, storage, move, drop and failure transitions |
| Optimization | Revalidate affected facts and compare modeled observable behavior before/after selected transformations |
| LLVM/runtime | Execute accepted fixtures at O0/O3; check cleanup/output and applicable generated-program sanitizer evidence |
| Driver/LSP | Present the same source rejection and related locations, including semantic-only checking and changed snapshots |
| Verification tools | Consume a versioned restricted representation, reconstruct independent facts, and report coverage boundaries |

The independent model must not call production overlap, liveness, origin,
conflict, or cleanup decision routines. Share inert syntax/schema definitions
where useful, but list that shared code in the trusted-base inventory. Do not
change production phase authority by making a test oracle decide source meaning.

Use two inputs: small abstract programs rendered to GTI source, and an adapter
from supported compiler MIR into the model. The first avoids trusting production
borrow metadata for expected outcomes; the second challenges lowering and
optimization. The adapter must reconstruct effects from executable operations,
check consistency with metadata, and reject omitted effects/unsupported shapes.
It cannot simply copy an `accepted` bit or assume declared origins are true.

Existing MIR constant-evaluation infrastructure may supply inert operation
schemas or test utilities after audit. Reusing its production execution/ownership
decisions as the supposedly independent oracle would defeat the purpose. The
restricted memory interpreter is not a new constexpr engine or semantic authority.

No formatter or editor syntax change is needed. Located rejection tests must
cover CLI/LSP agreement, stale-snapshot invalidation, and the distinction between
user errors and internal verifier failures. Keep internal proof data out of
ordinary user diagnostics unless it helps explain an actual borrowing error.

## Compatibility and migration

Existing accepted permissions remain unchanged by this RFC. If testing finds an
unsound acceptance, repair it as a safety bug with a regression and appropriate
changelog; valid programs must not be arbitrarily rejected to simplify the model.
Conservative rejections are tracked separately from unsound acceptance.

Version models, adapters, proof artifacts, and evidence manifests together. A new
language feature must update its invariant coverage and declare whether it is
inside the proved profile. Do not carry proof status across changed rules without
rechecking it. Begin expensive generation/proofs as scheduled or focused jobs;
promote stable bounded checks to normal integration only with measured budgets.
The retired preview channel is not used.

## Safety and correctness

The intended core theorem is conditional: for a well-formed program in the
specified core, accepted by the verified reference analysis, execution preserves
its memory/permission invariants and cannot reach the modeled errors (invalid
storage access, incompatible access, uninitialized/moved reads, or invalid free).
Normal termination, divergence, and explicitly defined failure remain allowed.
No termination theorem or full functional correctness claim is implied.

Separate three claims in every evidence report:

1. **Rule soundness:** the formal rules imply safety in the defined memory model.
2. **Algorithm correctness:** the executable reference analysis enforces those
   rules, including conservative joins and terminating fixed-point computation.
3. **Production correspondence:** supported production source/MIR agrees with the
   model or passes an independently checked translation obligation.

Generated agreement does not prove claim 3 for all compiler inputs. A per-artifact
certificate or translation validator only warrants claims for artifacts actually
checked and within its profile. LLVM and machine execution remain outside the
initial formal theorem and receive execution/regression evidence.

Audit safe wrappers that rely on unsafe implementations separately. Initially,
model only explicitly specified allocation/free primitives; record their trusted
contracts. More general safe APIs need implementation-specific invariant proofs
or checked execution coverage, not an exemption based on a `std::*` name.

## Performance and resource costs

Verification tooling should add no allocations, checks, or proof metadata to
ordinary shipped program execution. Runtime borrow instrumentation, if used in
tests, is opt-in and must not be mistaken for production performance.

Measure compiler time/peak memory, model/proof time, generated-program count and
shape coverage, minimization cost, artifact size, and CI minutes. Measure native
O0/O3 output and cleanup for representative reference-return, temporary-call,
owner replacement, and container workloads. No speedup or budget is claimed here.
Any change to default compiler checks needs before/after compile-time measurements;
any generated-code change also needs runtime, allocation and code-size evidence.

Bound enumeration by owners, fields, loans, control-flow nodes, call depth and
execution steps. Report all bounds and exceeded limits. Formal safety is not
bounded by these test sizes; exhaustive testing is. Cap fuzz workers and reducer
resources, retain failing seeds, and run heavy work under repository scheduling
rules rather than competing with every PR build.

## Alternatives and tradeoffs

- **More handwritten tests only:** fastest immediate value and necessary in phase
  1, but weak against unanticipated interactions and shared mistaken assumptions.
- **Production MIR verifier only:** preserves fail-closed checks cheaply, but
  shares representations and some semantic machinery with the compiler.
- **Differential checking against Rust:** useful inspiration and translated
  examples, but Rust is not an oracle for GTI's distinct rules or cleanup model.
- **ASan/UBSan/TSan only:** useful for executed bugs in instrumented components;
  they do not establish the complete borrowing contract. Instrumenting the host
  compiler does not instrument the GTI programs it generates.
- **Full compiler verification first:** strongest possible ambition, but defers
  practical protection and creates an unbounded initial commitment. A stated,
  useful core with an extension ledger makes proof scope reviewable.
- **A completely separate second compiler:** costly and likely to duplicate
  bugs. Prefer a small independent model and narrow, tested translation boundary.

## Unresolved questions

- Select the proof assistant and reference implementation strategy before phase
  2's model format is frozen. Prefer a route to extracted executable checking or
  a mechanically proved refinement; choose based on a small reproducible
  ownership/join proof, maintenance skills, and toolchain availability. The RFC
  does not preselect Lean, Rocq/Coq, or another system without that evidence.
- Decide whether initial production correspondence uses checked certificates or
  direct translation validation. Either must validate executable effects and
  adapters; differential tests alone cannot close phase 3.
- Set measured PR versus scheduled resource budgets and name maintainers for the
  model, generator, and proof artifacts before enabling mandatory jobs.
- Prioritize extension proofs after the mandatory core: dynamic indexed places,
  retained-owner/carrier graphs, recursion/closures, then concurrency and unsafe
  library contracts. This ordering is provisional; a discovered safety gap can
  change priority immediately.

These choices are prerequisites within the phases, not permission to postpone
all useful testing. Acceptance of the RFC must confirm the core scope and the
three separate exit gates.

## Implementation plan

All three phases are proposed, not started by publishing this RFC. Implementation
belongs in GTI (or an explicitly approved companion verification package), with
execution records linked from the existing ownership/implementation plans. Each
phase retains and runs the preceding phase's checks.

### Phase 1 — Make enforcement failures observable

**Outcome:** systematic tests detect concrete missing borrowing checks and broken
transport/cleanup now, without requiring an independent interpreter.

**Work:**

1. Inventory current rules and existing tests on a pinned main revision. Map each
   invariant to its authoritative source rule, semantic implementation, MIR
   obligations, positive/negative fixtures and known exclusions.
2. Add missing paired tests and an explicit interaction matrix: borrowing versus
   move/drop/replace; reborrowing versus parent access; escaping results versus
   temporaries; carriers versus owner lifetime; calls/constructors versus failure;
   joins/loops versus initialization; generics and closures versus origin facts.
   Include unrelated user-defined types alongside stdlib clients.
3. Add targeted compiler-check mutations and malformed-MIR mutations. Disable or
   invert a representative conflict check, erase a dependency, falsify an origin,
   retire a loan early, move an owner while borrowed, and reorder cleanup. Record
   which designated test detects each; a random earlier parser error is not a
   successful enforcement test.
4. Execute accepted cases at LLVM O0/O3, checking values, deterministic cleanup
   order/count, success, defined failure and partial construction. Add bounded
   CLI/LSP checks for representative rejects and semantic-only checking.

**Exit gate:** every inventory obligation has a positive/negative pair or a
reviewed reason why that pairing does not apply; every listed interaction has a
fixture or an explicit unresolved gap. Mandatory mutations for overlap, escape,
owner liveness, initialization and cleanup must be caught for the intended reason.
No unexplained surviving mandatory mutation or known in-scope accepted unsafe
program may be hidden by a percentage score. Add regression fixtures for findings
and demonstrate their intended failure on the parent when practical. Complete
focused owning/consumer tests, compiler_pipeline and native smoke under current
GTI policy. Publish the inventory, mutation results, unresolved coverage gaps,
source identities and replay commands.

**Assurance gained:** observed enforcement and a durable regression barrier.
**Still unproven:** untested interactions, the correctness of the rules, and
agreement between compiler layers that share the same faulty assumption.

### Phase 2 — Search independently for counterexamples

**Prerequisite:** phase 1 gate; agreed model profile, adapter format, and a viable
path to machine-checked proofs. Start from the mandatory sequential core above.

**Outcome:** an executable reference analysis and a separate concrete
memory/permission execution model can expose disagreements that the production
checker and verifier both miss.

**Work:**

1. Specify core storage, epochs, places, permissions, reborrow relationships,
   transitions, call contracts and failure cleanup without importing production
   decision routines. Review semantics against the invariant inventory.
2. Implement the small reference analysis and concrete interpreter. Validate each
   using hand-derived positive/negative traces and intentional faults in the
   model itself. Execute accesses against concrete storage/permission state;
   don't merely replay production `Borrow`/`EndBorrow` claims.
3. Generate both valid-by-construction and deliberately invalid programs. Enumerate
   all well-formed combinations within a published small bound; extend coverage
   with seeded structured fuzzing. Exercise branches, loop fixed points, call
   summaries, lifetime epochs and failure paths, not only straight-line syntax.
4. Compare independent decisions with semantic-only and full compiler outcomes.
   For admitted programs, compare reference execution, supported pre/post-
   optimization MIR, and LLVM O0/O3 observations. Use finite input enumeration
   where specified; label sampled inputs honestly. Minimize mismatches while
   preserving the original classification and violated invariant.
5. Add metamorphic checks only for justified transformations (for example alpha
   renaming). Scope changes and evaluation-order changes are not assumed neutral.
   Add safe-wrapper examples to production runtime tests without pretending they
   fall inside the core theorem if they do not.

**Exit gate:** the whole mandatory core is represented; the selected exhaustive
bounds, exact case counts, seeds, unsupported cases, timeouts and coverage by
operation/interaction are recorded. The scheduled generator and reducer reproduce
seeded unsound acceptances, conservative rejections, lowering errors and model
faults as different categories. Every disagreement in the acceptance corpus is
resolved or classified with evidence; any confirmed in-scope unsound acceptance
blocks closure. Retain regressions and a bounded deterministic corpus in CI, with
larger scheduled exploration. A clean fuzz campaign alone cannot close the gate.

**Assurance gained:** independently exercised rules, counterexample discovery and
bounded exhaustive evidence. **Still unproven:** unbounded soundness and general
compiler correspondence; the model and interpreter may themselves contain bugs.

### Phase 3 — Prove the core and check its compiler connection

**Prerequisite:** stable phase 2 model and corpus; selected proof environment and
reviewed theorem/trusted-base statement. Do not silently shrink the core to make
proof completion easier.

**Outcome:** machine-checked soundness for the stated core, plus an executable
independent check connecting supported compiled artifacts to that result.

**Work:**

1. Formalize operational memory semantics and ownership typing/analysis rules.
   Prove state preservation and absence of the named modeled memory violations;
   include reborrow restoration, invalidation after move/free, joins/loops,
   return-origin substitution, temporary endpoints, and defined-failure cleanup.
2. Prove the reference checking algorithm sound against those rules, including
   fixed-point convergence and conservative overlap/joins. Use extracted checking
   code or prove correspondence to the executable reference implementation; a
   separate unconnected paper algorithm is insufficient.
3. Implement a restricted translation validator or proof-certificate checker for
   production MIR artifacts. State and prove its validation implication against
   the formal core. Validate actual effect/CFG and call-contract correspondence,
   not only self-reported metadata. Check pre/post-optimization obligations and
   loan-erasure assumptions. Unknown shapes return unsupported, never verified.
4. Challenge the validator with forged certificates, omitted effects, false call
   summaries, premature frees, stale epochs and optimizer-introduced alias
   violations. Replay phase 2 counterexamples through the proof-backed path and
   retain LLVM O0/O3 runtime checks beyond the theorem's boundary.
5. Publish proof scripts, reproducible dependency versions, assumption audit,
   extraction/adapter trust boundaries, artifact coverage and remaining extension
   obligations. Keep the proof build and bounded certificate corpus in CI.

**Exit gate:** all core theorems compile in the selected proof checker with no
admitted obligations or unreviewed axioms; any explicit trusted assumptions are
listed and reviewed. The executable analysis is connected to those proofs, and
the validator's stated implication is checked. All mandatory core constructs
are covered by actual checked compiler artifacts; out-of-profile cases are
reported separately. Forgery tests and earlier regression/generation gates pass.
An independent review of the theorem scope and compiler adapter is required;
self-certification by the implementation author alone does not close the gate.

**Assurance gained:** formal core soundness and validated correspondence for the
supported artifacts actually checked. **Still unproven:** the entire GTI source
frontend, unsupported language families, arbitrary unsafe code, LLVM/native
correctness, and concurrency. Publish those limitations next to the proof claim,
with extension prerequisites; never advertise this as “GTI is fully verified.”

## Validation and release criteria

Each phase is separately deliverable under the gate above. The three gates are
cumulative and must not be collapsed into a final demo. Evidence records include
claims, scope, assumptions, tool/source identities, commands, results, failures,
coverage exclusions, and artifact retention paths. Green document checks prove
only that this proposal is well formed.

Implementation PRs use focused checks and optimized GTI compilers. Queue and
post-integration CI, platform inventories, and scheduled sanitizers follow current
GTI policy; do not duplicate the full suite locally or dispatch retired preview
work. Native checks run LLVM O0/O3. Distinguish host-compiler sanitizers from
instrumentation of generated GTI programs; where the latter is unavailable,
record that gap rather than substituting the former as equivalent evidence.

Update canonical ownership, MIR and verification documentation with each landed
phase. Add runnable examples if implementation introduces a user-facing capability;
this proposal alone adds no source feature. No phase claims release inclusion
without the relevant merged implementation and published toolchain evidence.

## Decision record

2026-11-06: The owner requested a three-phase verification plan in the RFC
repository. This authorizes drafting/publication, not design acceptance,
implementation, or merging the proposal. No design decision has been recorded.

## References

- [GTI ownership and lifetimes](https://github.com/lang-gti-official/gti/blob/ea499038dfbd68c6b5975c68a2d14319ea1436be/docs/language/ownership-and-lifetimes.md): inspected language contract and capability boundaries.
- [Place identity and ownership-state authority](https://github.com/lang-gti-official/gti/blob/ea499038dfbd68c6b5975c68a2d14319ea1436be/docs/plans/place-and-ownership-state.md): existing invariants, shared machinery and phase ownership; retain its history.
- [GTI MIR architecture](https://github.com/lang-gti-official/gti/blob/ea499038dfbd68c6b5975c68a2d14319ea1436be/docs/architecture/mir.md) and [verification evidence](https://github.com/lang-gti-official/gti/blob/ea499038dfbd68c6b5975c68a2d14319ea1436be/docs/architecture/verification.md): existing verifier responsibilities and mutation coverage.
- [Frontend MIR failure handling](https://github.com/lang-gti-official/gti/blob/ea499038dfbd68c6b5975c68a2d14319ea1436be/src/compiler/frontend.cpp) and [temporary-loan tests](https://github.com/lang-gti-official/gti/blob/ea499038dfbd68c6b5975c68a2d14319ea1436be/tests/scalar_temporary_borrow_tests.cpp): source evidence for current fail-closed behavior and forgeries.
- [GTI PR #266](https://github.com/lang-gti-official/gti/pull/266): motivating caught cleanup-order defect; publication is not release evidence.
- [GTI issue #179](https://github.com/lang-gti-official/gti/issues/179): related caller/callee origin contracts for borrow-carrying results, illustrating an extension obligation rather than an existing verification proposal.
- [ADR 018](https://github.com/lang-gti-official/gti/blob/ea499038dfbd68c6b5975c68a2d14319ea1436be/docs/decisions/018-loan-erasure-representation.md), [ADR 008](https://github.com/lang-gti-official/gti/blob/ea499038dfbd68c6b5975c68a2d14319ea1436be/docs/decisions/008-safe-concurrency-memory-model.md), and [ADR 012](https://github.com/lang-gti-official/gti/blob/ea499038dfbd68c6b5975c68a2d14319ea1436be/docs/decisions/012-outcome-first-systems-readiness.md): representation, concurrency and performance boundaries.
- [Rust compiler tests](https://rustc-dev-guide.rust-lang.org/tests/intro.html): practical layered compiler testing, not a general safety proof.
- [Miri](https://github.com/rust-lang/miri): checked execution and experimental aliasing models; executed-path evidence, not verification of all rustc behavior.
- [RustBelt, POPL 2018](https://plv.mpi-sws.org/rustbelt/popl18/): machine-checked safety for a realistic Rust subset and selected unsafe library abstractions, not the entire production compiler.
- [Polonius modeling goals](https://goals.rust-lang.org/2026/polonius.html): proposed formal modeling and independent-oracle validation; goals are not completion claims.
- [Sound Borrow-Checking for Rust via Symbolic Semantics](https://arxiv.org/abs/2404.02680): research connecting a borrow-centric symbolic model to lower-level memory execution; inspiration for a GTI-specific proof boundary.
- [Open procedural-macro RFC](https://github.com/lang-gti-official/rfcs/pull/1): checked for overlap; distinct proposal, with provisional RFC number 0001.
