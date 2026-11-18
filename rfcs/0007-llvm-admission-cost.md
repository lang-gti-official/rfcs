# RFC 0007: Faster LLVM admission planning

| Field | Value |
| --- | --- |
| Status | draft |
| Authors | @gti-language-official (with Claude Code) |
| Created | 2026-11-18 |
| Updated | 2026-11-18 |
| Area | compiler |
| Proposal | https://github.com/lang-gti-official/rfcs/pull/8 |
| Decision | pending |
| Implementation | none |
| Supersedes | none |
| Superseded by | none |

## Summary

Before the LLVM backend lowers anything, `planLlvmAdmission` works out what
the program needs and whether the backend supports it. It is the largest
serial cost in the backend: about 60% of backend time at `-O0`, and about a
quarter at `-O2`. Profiling shows that most of that time does not go on
admission decisions. It goes on overhead around them, in three places:

- **Exceptions as answers.** Cached "unknown" results are replayed by
  rethrowing C++ exceptions.
- **Uncached type queries.** Recursive representation queries are never
  memoized, and they look types up by scanning whole lists with deep
  structural equality.
- **Slow coverage bookkeeping.** Each recorded use is counted in a map keyed
  by tuples of strings.

This RFC proposes four changes that keep every admission decision, diagnostic
and coverage record byte-for-byte the same:

- non-throwing outcomes;
- type-keyed indexes built once per plan;
- memoized whole-type queries;
- integer coverage keys.

It also proposes the evidence that must show the decisions are unchanged. This
is a draft, not an implementation claim. It is the separate track that
[RFC 0006](https://github.com/lang-gti-official/rfcs/pull/7) calls out, and it narrows the serial
share that limits parallel code generation.

## Motivation and goals

### Current behavior (source at `main` 1302b77e5)

`LlvmBackend::generate` calls `planLlvmAdmission`
([`src/compiler/llvm/admission.cpp:6210`][plan]) before creating any LLVM
session. The planner:

1. Opens a `HierarchyStorageScope`, a per-program cache of
   `containsHierarchyStorage` outcomes added in GTI #387.
2. Computes the reachable closure.
3. Builds `StaticDispatchProofs` ([`admission.cpp:335`][proofs]). For every
   required body, place and instruction it asks whether a type contains
   hierarchy storage (`contains`, `related`, `referent`).
4. Runs an `Inventory` ([`admission.cpp:2951`][inventory]) over every lowered
   body, needed or not. For each body, block, instruction, operand, type node,
   trait and drop recipe, the inventory records a coverage use with
   `add(value, shape)`.

Several structures behind this are expensive by design:

- **Rejections are thrown.** `containsHierarchyStorage`
  ([`placement.cpp:834`][chs]) fails closed by throwing
  `BackendUnsupportedError` when storage is unknown, missing or cyclic. The
  cache stores that rejection as a `std::exception_ptr` and calls
  `std::rethrow_exception` on every later hit. `StaticDispatchProofs::contains`
  and several other members immediately catch it and return `false`
  ([`admission.cpp:582`][contains]). A type that is rejected once therefore
  throws on every query about every place or instruction of that type.
- **Representation queries are never cached.** `NativeValues::operator()`
  ([`admission.cpp:167`][natives]) answers "is this a native value type?" by a
  fresh recursive walk with four new `std::set`s per call. Each class node
  finds its instance by scanning `program.classInstances()` with
  `SemanticType` equality. Integral enums are found the same way, and so are
  payload enums, through `MirProgram::findPayloadEnum`
  ([`include/gti/mir.h:2080`][find]).
- **Equality is deep.** `SemanticType::operator==` is a defaulted,
  member-wise comparison that recurses into nested argument vectors
  ([`include/gti/semantic_core.h:684`][eq]).
- **Type walks repeat.** `Inventory::type` walks a type's whole tree each time
  an operand, trait or drop names it. Each node runs the native-C contract
  checks and `representationShape`. `Inventory::cleanup` walks a drop recipe's
  whole tree for every drop obligation and lifecycle event.
- **Coverage keys are strings.** `Inventory::add` de-duplicates uses in a
  `std::map` keyed by a tuple that starts with two `std::string_view`s, the
  coverage family and name ([`admission.cpp:4966`][add]).

### Measurements

These were taken on 2026-11-18 with the gtiup `tip` toolchain installed on
2026-11-17, which reports 0.494.0. The host was macOS arm64 with 12 logical
CPUs and a load of about 1. The figures come from 1 ms `sample` profiles of
`-O0` compiles. One sample is about 1 ms of one thread.

| Program | Backend | Admission | Share of backend |
| --- | --- | --- | --- |
| 091-json-documents | 419 ms | 266 ms | 63% |
| 093-http-json-client | 609 ms | 360 ms | 59% |
| 141-reflected-json | 488 ms | 313 ms | 64% |
| 194-regular-expressions | 461 ms | 284 ms | 62% |

At `-O2` the same programs spend 25–28% of the backend in admission, about the
same absolute time, because LLVM optimization takes the rest. Across the
203-example corpus, the backend is 12% of `-O0` wall time and the
second-largest phase.

Where admission time goes, pooled across the four programs (1,223 samples).
The categories overlap, because inclusive time is attributed to each frame on
the stack:

| Inclusive share of admission | |
| --- | --- |
| `Inventory::inspect` | 62% |
| `StaticDispatchProofs` construction | 31% |
| `NativeValues::operator()` (from both of the above) | 39% |
| Deep `SemanticType::operator==` | 33% |
| `containsHierarchyStorage` | 31% |
| C++ exception propagation (`rethrow_exception`, unwinding, dyld unwind-section lookup) | 28% |
| `Inventory::add` map insertion | 7% |

Attribution of the main leaves:

- **Exception propagation.** Essentially all of it comes from
  `containsHierarchyStorage` replaying a cached rejection under the
  `StaticDispatchProofs` constructor. On macOS each throw also looks up
  unwind sections through dyld, which is why it is so expensive.
- **Deep equality.** Most of it (about 21 of the 33 points) is under
  `NativeValues::operator()`, which compares class-instance types inside its
  linear scans. The rest is spread across `Inventory::type`, `classShape` and
  the native-C declaration contracts.

To give a sense of scale, 093's MIR has 1,123 bodies, 146 class instances, 31
payload enums and 24 integral enums.

### Goals

- **Speed.** Make admission at least 2× faster on the programs above. This is
  a target for acceptance, not a measured result.
- **Exact equivalence.** Keep the admission plan exactly the same:
  - required bodies and closure kind;
  - the first unsupported use and its limitation message;
  - the ordered coverage use list, including each entry's occurrence count;
  - LLVM output.
- **Precise structural fixes.** Remove each overhead at its cause, as general
  data-structure changes. Add no special cases for particular programs or
  library types.

## Non-goals

- **Changing what is admitted, or any diagnostic.** That includes the order in
  which the first unsupported use is found.
- **Skipping the inventory for unreachable bodies.** It may be a later saving,
  but it changes the recorded coverage evidence, which needs its own decision.
- **Running admission in parallel.** Removing repeated work comes first.
  RFC 0006 covers backend parallelism.
- **Interning `SemanticType` across the whole compiler.** That is a broader
  change affecting semantics, HIR and MIR (see
  [Alternatives](#alternatives-and-tradeoffs)).
- **Caching admission across compilations.** The plan depends on the whole
  program.

## Guide-level design

There is no user-visible syntax, option or diagnostic change. Users see faster
backend compiles, most at `-O0`. `gti --time-trace` gains these regions:

- `llvm-admission`;
- `llvm-admission-closure`;
- `llvm-admission-dispatch-proofs`;
- `llvm-admission-inventory`.

These are shared with RFC 0006 stage A. Under `GTI_COMPILER_VALIDATION` the
planner also reports query counters: hierarchy-storage queries, cache hits and
rejections, native-value queries and memo hits, and type-walk replays. They
make regressions visible in the structural snapshot.

## Semantic rules

No GTI language rule changes. These are rules about the compiler's internals.

1. **Unknown stays fail-closed.** `containsHierarchyStorage`'s "unknown,
   missing or cyclic storage fails closed" contract
   ([`placement.h:43`][chs-doc]) keeps its meaning. A result is now one of
   *contains*, *excludes* or *unknown, with a reason*, rather than a boolean
   or an exception. Callers that currently catch and return `false` read
   *unknown* as `false`. Callers that currently let the exception propagate
   get the same `BackendUnsupportedError`, with the same message, from a thin
   throwing wrapper.
2. **Only whole-type answers are cached.** A memoized answer is stored only for
   a top-level query, as `HierarchyStorageScope` already does. Answers for
   nested types may depend on the inline containment path (the `visiting` and
   `crossed` sets), so they are never cached. The top-level answer depends only
   on:
   - the type;
   - the immutable program;
   - the target;
   - the query's pointee predicate.

   Each pointee predicate must itself be a pure function of those. Where it
   reads `StaticDispatchProofs` state, that state is complete before any
   memoized query runs.
3. **Index lookups must match the scans.** The index answers exactly what the
   current linear scan returns. That includes the scan's own failure case:
   `NativeValues` treats two class instances with an equal type as "not
   native". The index keeps that by recording duplicates, not by keeping the
   first match.
4. **Coverage records are unchanged.** Coverage use identity, occurrence counts
   and insertion order are unchanged. A memoized type walk records the exact
   sequence of `add(value, shape)` calls its first walk made, for that type and
   for the `executable` and `required` context bits that affect the record. It
   replays them in order, so occurrence counts and first-use positions match.

## Compiler and tooling design

All changes are in the LLVM backend's admission layer: `src/compiler/llvm/`,
plus optionally a read-only index accessor on `MirProgram`. No
syntax, semantics, HIR or MIR phase changes.

### 1. Non-throwing hierarchy-storage outcomes

- **Return a value, not an exception.** `computeHierarchyStorage`
  ([`placement.cpp:502`][compute]) returns a
  `HierarchyStorageOutcome { Contains | Excludes | Unknown(reason) }` from its
  recursive visitor, instead of throwing out of it.
- **Two entry points:**
  - `classifyHierarchyStorage(program, type)` is new and never throws;
  - `containsHierarchyStorage(program, type)` keeps its signature and throwing
    contract by wrapping it.
- **The cache stores the outcome value.** Today it stores an `exception_ptr`.
- **Callers that only want a boolean read the outcome directly.** These are
  `StaticDispatchProofs::contains`, `related`, `referent`, and the
  catch-and-return-`false` sites at [`admission.cpp:582`, 622, 714, 747, 763,
  779, 827 and 847][contains]. They no longer use try/catch.

This alone should remove the 28% of admission spent propagating exceptions.

### 2. Type-keyed indexes for the plan

- **Build the indexes once.** A `TypeIndex` is built once per
  `planLlvmAdmission`, after the program is sealed and immutable. It maps a
  `SemanticType` to:
  - its class instances, as a list so duplicates stay visible;
  - its payload enum;
  - whether it is an integral enum.
- **Hash once, compare once.** It uses the existing structural `outcomeHash`
  ([`placement.cpp:779`][hash]) with full equality on a hit, so each lookup
  does one deep comparison instead of up to one per class instance.
- **Wire it in.** `NativeValues`, `Inventory::classShape` and the other scans
  take the index.
- **Optionally share it.** `MirProgram::findPayloadEnum` is also a linear scan,
  used throughout MIR effects. The index could move onto `MirProgram` as a
  lazily built, read-only accessor once the program is sealed. That needs a
  clear invalidation story while MIR is still being changed, so it is an
  [unresolved question](#unresolved-questions).

### 3. Memoized whole-type queries

- **`NativeValues`.** Cache the top-level answer of
  `NativeValues::operator()` per type, for each `NativeValues` instance (one
  for `StaticDispatchProofs`, one for `Inventory`, because their pointee
  predicates differ). Allocate the four path sets once per query rather than
  per call. Rule 2 above sets what may be cached.
- **`Inventory::type` and `Inventory::cleanup`.** Cache the `add` sequence a
  walk produced, keyed by the root type or drop recipe and the context bits.
  Replay it rather than walking again (rule 4).
- **`representationShape` and `classShape`.** Cache these per type if the new
  profile still shows them after the changes above.

### 4. Integer coverage keys

`Inventory::add`'s de-duplication key replaces the two leading string views
with the identity of the `LlvmCoverageEntry` (and of the shape entry). Those
entries come from a static table, so the change preserves uniqueness. The
`std::map` becomes a hash map. Insertion order into `uses` does not change,
because `uses` stays a vector appended on first insertion.

### Validation-mode cross-checks

Under `GTI_COMPILER_VALIDATION`:

- each memo or index hit is recomputed the old way and compared;
- a mismatch is an internal compiler error that names the query and type.

These checks are off in ordinary compiles, following the proportionate
self-check policy. A test-only `--dump-llvm-admission` (or an equivalent
harness entry point) writes the whole `LlvmAdmissionPlan`: closure, bodies,
ordered coverage uses with occurrences, and the first unsupported use. That
lets the corpus check equivalence (see
[Validation](#validation-and-release-criteria)).

## Compatibility and migration

- **No user-visible change.** There is no source, option, diagnostic or output
  change.
- **Unchanged outputs.** `--emit-llvm` text, objects and executables must stay
  byte-identical, so caches stay valid and need no schema change.
- **Internal callers.** The `containsHierarchyStorage` throwing API keeps its
  signature for existing callers. The non-throwing API is added beside it.
- **Prior decisions.** No ADR, specification or RFC is revised. This refines
  GTI #387's cache.

## Safety and correctness

Admission is a fail-closed gate. It must never admit a program, or a use
shape, that it rejects today, and it must never reject something it admits
today. The risks are:

- a memo returning a path-dependent nested answer;
- an index losing a duplicate the old scan treated as a rejection;
- a replayed coverage sequence that differs in order or count;
- a non-throwing outcome that is read as `false` where the old code let the
  exception propagate and reject.

Each is covered:

- **Memo scope.** Only top-level answers are cached (rule 2), and a
  validation-mode recomputation checks every hit.
- **Duplicates.** The index keeps duplicates, with a unit test for the
  duplicate-class case.
- **Propagation sites.** Every current `catch (const BackendUnsupportedError
  &)` site is converted on purpose, and the sites that propagate keep using the
  throwing wrapper. A test drives an unknown-storage type through both kinds
  of site.
- **Whole-plan check.** The corpus equivalence gate compares the full plan
  dump, not just executables. Matching outputs alone would not prove that
  admission decisions are unchanged.

## Performance and resource costs

- **Expected effect** (estimates from the profile, to be measured):
  - non-throwing outcomes remove most of the 28% of admission in exception
    propagation;
  - indexes and memoized `NativeValues` queries remove most of the roughly 21
    points of deep equality under `NativeValues`, plus the repeated walks;
  - integer coverage keys save most of the 7% in map insertion.

  Together that is the 2× target. At `-O0` this is roughly a 25–35% faster
  backend and a 4–7% faster whole compile on these programs. That is more than
  RFC 0006's 2–3% ceiling for parallel code generation at `-O0`, and it
  carries no reproducibility risk.
- **Memory.** The memo tables and indexes are proportional to the number of
  distinct types and drop recipes. That is small next to the MIR, but peak RSS
  must be measured.
- **No runtime effect.** Generated code is byte-identical.

## Alternatives and tradeoffs

1. **Keep the current planner.** It costs 0.25–0.4 s on each of the larger
   examples, and more on larger programs. Admission stays the cap on RFC
   0006's parallel gains.
2. **Intern `SemanticType` everywhere** (hash-consing, pointer equality). This
   would make every type comparison O(1) across the compiler, and frontend
   phases with deep-equality hotspots (for example `typeTraits`) would benefit
   too. But it is a cross-phase representation change with lifetime and
   ownership questions. The local indexes here get most of admission's
   benefit now and do not block it later.
3. **Run admission in parallel.** Per-body inventory is mostly independent,
   but `StaticDispatchProofs` and the coverage list are shared and
   order-sensitive. Threading would reproduce the repeated work on every core
   and complicate the deterministic first-unsupported ordering. Rejected until
   the repeated work is gone.
4. **Skip inventory for unreachable bodies.** This could be a large saving,
   since all 1,123 bodies are inspected, not only reachable ones. But it
   changes the recorded coverage evidence, so it needs a decision on what
   coverage records for dormant bodies. Deferred to a follow-up.
5. **Fold admission into lowering**, rejecting while lowering. That removes a
   pass, but loses "reject before creating any LLVM state" and the complete
   coverage inventory. Rejected.

The tradeoff the owner would accept: a few caches and indexes in the
admission layer, with validation-mode cross-checks, for a faster backend and
no change in behavior.

## Unresolved questions

1. **Where the type index lives.** Keep it admission-local, or add it to
   `MirProgram` (with lazy construction once the program is sealed) so that
   `findPayloadEnum` and MIR effects benefit as well?
2. **The dump format.** Should the admission-plan dump be a CLI option for
   tests only, or a harness entry point in an existing test runner? The old
   suite is frozen against new `add_test` registrations, so new coverage
   should go into the `gti-test` UI runner.
3. **Acceptance target.** Is a 2× admission speed-up the right target, or
   should acceptance be stated as a share of the backend?
4. **Follow-ups.** Should skipping the inventory for unreachable bodies be
   folded into this RFC, or remain a follow-up?

## Implementation plan

Each slice is a separate PR in `lang-gti-official/gti`. Every slice must leave
the corpus admission-plan dump and `--emit-llvm` output byte-identical.

1. **Telemetry and equivalence harness.** Add the admission time-trace
   regions, the validation-mode counters, and the admission-plan dump, then
   record baseline dumps for the example corpus.
2. **Non-throwing hierarchy-storage outcomes.** Convert the
   catch-and-return-`false` sites.
3. **Plan-wide type index.** Wire it into `NativeValues` and the
   class-shape lookups.
4. **Memoized `NativeValues` and type/cleanup walk replay.** Include the
   validation-mode cross-checks.
5. **Integer coverage keys.**
6. **Measure and record.** Record the results in
   `docs/plans/performance-tooling.md`, then decide on the follow-ups.

## Validation and release criteria

- **Equivalence:**
  - For every example, and for the LLVM admission and coverage test inputs,
    the admission-plan dump and `--emit-llvm` output are byte-identical before
    and after each slice, at `-O0` and `-O2`.
  - Rejected programs report the same first unsupported use and message.
- **Validation mode:**
  - The corpus and focused suites pass with `GTI_COMPILER_VALIDATION=1`, so
    every memo and index hit is recomputed and compared.
  - An injected wrong memo entry is reported as an internal compiler error.
- **Targeted cases:**
  - an unknown-storage type queried through both catching and propagating
    sites;
  - duplicate class-instance types;
  - recursive owner and payload cycles (`crossed` versus `visiting`);
  - coverage occurrence counts for repeated operands of one type.
- **Existing gates:** the LLVM admission, coverage-evidence and
  coverage-exhaustiveness tests, the backend suites, `compiler_pipeline`, and
  the runtime suites.
- **Performance:**
  - Report admission time, backend time, total wall and CPU time, and peak RSS
    for 091, 093, 141 and 194, and for the corpus, at `-O0` and `-O2`, before
    and after.
  - The admission target is at least 2× faster on the four programs, with
    peak RSS no more than 5% higher.
- **Documentation:** the backend architecture document records the outcome
  type, index and memo rules. `performance-tooling.md` records the
  measurements.

## Decision record

No design decision yet.

## References

- [`src/compiler/llvm/admission.cpp`][plan]: `planLlvmAdmission`,
  `StaticDispatchProofs`, `NativeValues` and `Inventory`, the code this RFC
  restructures.
- [`src/compiler/llvm/placement.cpp`][chs] and [`placement.h`][chs-doc]:
  `containsHierarchyStorage`, its fail-closed contract, and the
  `HierarchyStorageScope` cache that replays rejections as exceptions.
- [`include/gti/mir.h`][find] and [`include/gti/semantic_core.h`][eq]: linear
  by-type lookups and defaulted deep `SemanticType` equality.
- GTI #387: the per-program hierarchy-storage outcome cache. It measured −5%
  to −27% CPU at `-O0` on the heavy examples when it landed, and this RFC
  removes its remaining exception replay.
- GTI #418: precedent for keeping integrity re-checks in validation mode only.
- [RFC 0006 draft](https://github.com/lang-gti-official/rfcs/pull/7):
  parallel LLVM code generation. It measures the backend breakdown, and its
  Amdahl bound depends on the serial admission share this RFC reduces.

[plan]: https://github.com/lang-gti-official/gti/blob/1302b77e5/src/compiler/llvm/admission.cpp#L6210
[proofs]: https://github.com/lang-gti-official/gti/blob/1302b77e5/src/compiler/llvm/admission.cpp#L335
[inventory]: https://github.com/lang-gti-official/gti/blob/1302b77e5/src/compiler/llvm/admission.cpp#L2951
[natives]: https://github.com/lang-gti-official/gti/blob/1302b77e5/src/compiler/llvm/admission.cpp#L167
[contains]: https://github.com/lang-gti-official/gti/blob/1302b77e5/src/compiler/llvm/admission.cpp#L582
[add]: https://github.com/lang-gti-official/gti/blob/1302b77e5/src/compiler/llvm/admission.cpp#L4966
[chs]: https://github.com/lang-gti-official/gti/blob/1302b77e5/src/compiler/llvm/placement.cpp#L834
[compute]: https://github.com/lang-gti-official/gti/blob/1302b77e5/src/compiler/llvm/placement.cpp#L502
[hash]: https://github.com/lang-gti-official/gti/blob/1302b77e5/src/compiler/llvm/placement.cpp#L779
[chs-doc]: https://github.com/lang-gti-official/gti/blob/1302b77e5/src/compiler/llvm/placement.h#L43
[find]: https://github.com/lang-gti-official/gti/blob/1302b77e5/include/gti/mir.h#L2080
[eq]: https://github.com/lang-gti-official/gti/blob/1302b77e5/include/gti/semantic_core.h#L684
