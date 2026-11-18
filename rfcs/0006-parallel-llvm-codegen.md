# RFC 0006: Parallel LLVM code generation units

| Field | Value |
| --- | --- |
| Status | draft |
| Authors | @gti-language-official (with Claude Code) |
| Created | 2026-11-18 |
| Updated | 2026-11-18 |
| Area | compiler |
| Proposal | pending |
| Decision | pending |
| Implementation | none |
| Supersedes | none |
| Superseded by | none |

## Summary

GTI compiles a whole program into one LLVM module and runs LLVM optimization
and machine-code generation over it on one thread. This RFC proposes to split
the module, once whole-program work is done, into a fixed number of *code
generation units*. Each unit gets its own `LLVMContext` and runs on its own
thread, and the driver links the resulting objects. The unit count, not the
thread count, determines the output, so builds stay byte-reproducible however
many threads they use.

The audit behind this draft finds that the design is sound and well
precedented, but that the time it can save today is small. "LLVM emission" is
the second-largest phase at `-O0`, but most of it is GTI's own serial
admission planning, not LLVM. LLVM machine-code generation is about a quarter
of the backend at `-O0`. At `-O2` the LLVM optimization pipeline adds roughly
half the backend. The proposal is therefore staged:

1. Measure the backend phase by phase.
2. Parallelize machine-code generation behind an option.
3. Only with evidence, parallelize the late optimization pipeline.

This is a draft, not an implementation claim.

## Motivation and goals

### Current behavior (source at `main` 12dda2a36)

`LlvmBackend::generate` ([`src/compiler/llvm_backend.cpp:222`][generate])
verifies the lowered program, then runs three steps:

1. **Admission.** `planLlvmAdmission` decides what the program needs and
   whether the backend supports it.
2. **Lowering.** One `native_llvm::Session` lowers every required MIR body into
   one `llvm::Module`.
3. **Emission.** `Session::emitObject` ([`session.cpp:895`][emit]) optimizes
   the module and produces the object.

The session owns one `LLVMContext`, one `TargetMachine` and one module
([`session.h:50`][session]). `emitObject` runs, in order and all on the
calling thread:

1. Debug-info finalization and IR verification.
2. Whole-program internalization of private GTI functions in sealed hosted
   executables ([`session.cpp:941`][internalize]).
3. GTI's module transforms: `promotePrivateScalarResults`, undefined-memory
   instrumentation, `tune-cpu` attributes and guarded dispatch promotion.
4. LLVM's per-module default pipeline ([`session.cpp:988`][pipeline]).
5. At `-O2`/`-O3`, further GTI module work: `specializeBoundedRecursion`, hot
   and cold splitting, one more simplification and optimization round,
   `foldInductivePointerLoops`, and a final round.
6. `reuseCheckedArithmeticResults`, then address or thread instrumentation.
7. A final verification.
8. One legacy code-generation pass manager that writes one object
   ([`session.cpp:1039`][codegen]).

`BackendArtifact` carries exactly one object ([`include/gti/backend.h:40`][artifact]).
The project cache stores one object representation
([`src/driver/build.cpp:284`][cache]). Linking goes through the selected
native compiler. On Apple hosts it adds `-Wl,-reproducible`, so that equal
inputs give equal bytes for serial/parallel build equivalence and cache
verification ([build-and-driver.md][driver-docs]).

There is already one kind of compile-level parallelism. `gti build --all` runs
independent whole-program target builds as concurrent child processes
(`--jobs`, defaulting to hardware concurrency). `gti_lsp` runs analyses on a
worker pool. Neither ever splits one program's backend work.

### Measurements

These were taken on 2026-11-18 with the gtiup `tip` toolchain installed on
2026-11-17, which reports 0.494.0. The host was macOS arm64 with 12 logical
CPUs and a load of about 1. Timings come from `gti --time-trace` phase regions,
with a 1 ms `sample` profile for the split inside the backend. The corpus is
the 203 programs in `examples/*.gti` that compile without per-example options
(the concurrent execution profile was retried where needed). Wall time
includes the native link.

| Corpus, 203 examples | `-O0` | `-O2` |
| --- | --- | --- |
| Wall time | 109.1 s | 173.7 s |
| `gti-semantics` | 52.7 s | 55.3 s |
| `gti-optimize` (GTI MIR optimizer) | 2.3 s | 47.3 s |
| `gti-backend` | 12.9 s (12% of wall) | 27.3 s (16% of wall) |
| LLVM machine-code generation (legacy codegen pass manager) | 3.3 s (25% of backend, 3.0% of wall) | 4.3 s (16% of backend, 2.5% of wall) |

The backend is the second-largest phase at `-O0`. At `-O2` it is third, behind
the MIR optimizer. Where backend time goes, sampled on the two largest-backend
programs:

| Share of `gti-backend` | 093 `-O0` | 141 `-O0` | 093 `-O2` | 141 `-O2` |
| --- | --- | --- | --- | --- |
| Admission (`planLlvmAdmission`, GTI, serial) | 61% | 64% | 25% | 28% |
| LLVM optimization pipeline | <1% | <1% | 52% | 48% |
| LLVM machine-code generation | 20% | 19% | 15% | 17% |
| IR lowering (`lowerScalarProgram`) | 5% | 5% | 2% | 2% |
| Verification, GTI module transforms, other | 14% | 12% | 6% | 5% |

Where the admission time goes:

- About 60% is in `Inventory::inspect`, mostly its `cleanup`, `type` and
  `operand` walks.
- About 30% is in `StaticDispatchProofs`, nearly all of it in
  `containsHierarchyStorage`.

### What parallel units could save

These are upper bounds from Amdahl's law. They assume four threads, perfect
scaling and no splitting overhead.

| Scope | Corpus `-O0` | Corpus `-O2` | 093 `-O0` (wall 3.76 s) | 093 `-O2` (wall 8.30 s) |
| --- | --- | --- | --- | --- |
| Machine-code generation only | ≤2.3% | ≤1.9% | ≤3% | ≤2.6% |
| Optimization and code generation | n/a | ≈≤8% (estimated) | n/a | ≤11.6% |

The `-O2` corpus figure for "optimization and code generation" is an estimate.
It applies the sampled optimization share to the corpus backend total.

### Goals

- Make backend time scale with available cores for large programs, without
  changing GTI semantics, safety checks or failure behavior.
- Keep output deterministic. The same inputs and unit count give
  byte-identical objects and executables at any thread count.
- Lay down unit boundaries that later work can reuse, such as per-unit object
  reuse across edits.

Success is a measured backend wall-time reduction on representative large
programs that is worth its memory, complexity and runtime-performance cost.
The thresholds are set under [Validation and release
criteria](#validation-and-release-criteria).

## Non-goals

- **Parallel semantic analysis, HIR/MIR lowering or the MIR optimizer.** These
  are the largest phases, but they need a query-style frontend and stable
  identities first. That is separate work.
- **Parallel IR construction.** Lowering each unit straight into its own
  `LLVMContext` would also need `Layouts`, `Abi`, `DebugInfo` and the text
  literal table to become per-context. Lowering is about 2–5% of the backend,
  so this does not pay for itself now.
- **Making admission faster.** It is the largest serial cost in the backend at
  `-O0`, but it is ordinary GTI code with no threading question in it, so it
  belongs in its own issue. It is listed here as a prerequisite, not designed
  here.
- **ThinLTO-style cross-unit importing.** See
  [Alternatives](#alternatives-and-tradeoffs).
- **Changing linkers, or splitting compiled-scalar and embedding libraries.**
  Library artifacts keep one unit (see
  [Semantic rules](#semantic-rules)).
- **Cross-target or C++ backend work.** The C++ backend is frozen. This
  concerns LLVM only.

## Guide-level design

Nothing changes in GTI source. The user-facing surface is the following
proposed driver options. The exact spelling is an open question.

```sh
# Proposed: split into 8 units, run them on up to 4 threads.
gti app.gti -O2 --codegen-units 8 --codegen-threads 4

# Proposed: current behaviour; a single unit, byte-identical to today.
gti app.gti -O2 --codegen-units 1
```

- `--codegen-units N` sets how many units the module is split into. It changes
  the generated code, for example symbol placement and which calls cross unit
  boundaries. So it is part of the artifact and cache identity, and it is
  fixed independently of the host. Until the measurements justify another
  value, the default stays `1`.
- `--codegen-threads T` bounds concurrency. It never changes output bytes. By
  default it is `min(N, hardware concurrency)`, reduced under
  `gti build --all` so that `jobs × threads` does not oversubscribe the host.
- `--emit-llvm` keeps printing the single optimized module as it is before the
  split, so textual IR tests and diagnostics are unchanged.
- `gti --time-trace` gains backend regions (`llvm-admission`, `llvm-lower`,
  `llvm-optimize`, `llvm-codegen`, `llvm-codegen-unit`) and LLVM's own pass
  regions. That makes the data above reproducible without a sampling
  profiler.

What fails:
- A unit count above a fixed maximum (proposed: 256), or zero, is a usage
  error.
- Library or embedding builds asked for more than one unit report a GTI
  limitation diagnostic rather than producing an object with extra global
  symbols. This lasts until partial linking is designed.

## Semantic rules

No GTI language semantics change. MIR stays the execution authority.
Splitting is a backend representation decision, made after every GTI- and
LLVM-level IR transform, so it must not change observable behavior. The
backend contract is as follows.

1. **Where the split happens.** The split happens after the final `verify()`
   in `emitObject`, once internalization, every GTI module transform, the
   optimization pipeline, and sanitizer and undefined-memory instrumentation
   have run on the whole module. In stage B no IR optimization runs after the
   split, so splitting cannot change optimized IR. It only changes
   machine-level decisions at unit boundaries.
2. **Every definition is emitted once.** Every function and global definition
   lands in exactly one unit. Nothing is duplicated, including:
   - text literals, whose single address per distinct literal
     ([`session.cpp:568`][literal]) must survive the split;
   - thread-local storage;
   - static initialization data;
   - native callback adapters.
3. **Symbols that cross units.** A private or internal symbol referenced from
   another unit is promoted to hidden external linkage under a deterministic
   name in the reserved `__gti_native_v1_` space. Nothing else changes
   linkage. Hidden symbols are not exported from the executable.
4. **Deterministic partitioning.** The partition depends only on the module's
   contents and `N`. It never depends on thread count, scheduling, addresses or
   host. Objects reach the linker in unit-index order.
5. **Diagnostics.** LLVM diagnostics from each unit context are collected and
   reported in unit-index order. Any error fails the whole emission, which
   never produces a partial object set.
6. **Artifacts that stay one unit.** For now these stay at `N = 1`:
   - compiled-scalar libraries and embedding libraries, whose object symbol
     tables are checked against an exact export set;
   - `--emit-llvm`.

   Instrumented builds may also stay at one unit (see
   [Unresolved questions](#unresolved-questions)).

## Compiler and tooling design

The work is owned by the LLVM backend (`src/compiler/llvm/`) and the driver.
No syntax, semantics, HIR or MIR phase changes.

### Stage A: backend telemetry (prerequisite)

- Add `PhaseTimeScope` regions inside `LlvmBackend::generate`, `planLlvmAdmission`
  and `Session::emitObject` for admission, lowering, GTI module transforms,
  the optimization pipeline and code generation.
- Register LLVM's time-profiling pass instrumentation, so new-pass-manager
  passes show up in `--time-trace`. Today only the legacy code-generation
  manager's `OptModule` and `RunPass` events appear.
- Extend the compiler structural snapshot or benchmark scripts to report the
  backend breakdown. No behavior change.

### Stage B: parallel machine-code generation

1. **Partition.** Use LLVM's `SplitModule` (TransformUtils) on the verified
   module. Its default mode groups globals that must stay together, such as
   comdats and aliases, and assigns groups by hashing names. That is
   deterministic but ignores source locality.

   The recommended alternative is a GTI-owned partitioner that assigns
   functions by owning source module or package from MIR provenance, then
   balances by instruction count. It gives better locality, and partitions
   stay stable across edits, which per-unit reuse would need.

   Either way, run `SplitModule`'s externalization rule, or an equivalent, for
   symbols referenced across units.
2. **Transfer.** Write each unit to in-memory bitcode, then on a worker thread
   parse it into a fresh `LLVMContext`, the same approach as LLVM's
   `splitCodeGen` in `llvm/CodeGen/ParallelCG.h`. Each worker builds its own
   `TargetMachine` with `makeMachine` and installs a diagnostic handler that
   records into its unit's slot.
3. **Threads.** Use GTI-owned threads with an explicit stack size, as
   `gti_lsp` does (8 MiB, because Darwin's default for secondary threads is
   small). Units go into a bounded work queue drained in index order. Prefer
   this to `splitCodeGen`'s internal thread pool, so that stack size,
   diagnostics and the thread budget stay under GTI's control.
4. **Artifacts.** `BackendArtifact` gains an ordered list of objects, and a
   single-object artifact is the `N = 1` case.

   This amends ADR 031's statement that `BackendArtifactKind::Object` is one
   relocatable object handed to `NativeLinkRequest`. `NativeLinkRequest`
   passes the objects in order, so Apple's `-Wl,-reproducible` and the
   staging-filename rule still apply. The project cache stores the ordered
   list under a new schema. The cache identity adds the unit count and the
   partitioner's version.
5. **Validation mode.** Under `GTI_COMPILER_VALIDATION`, check after the split
   that:
   - every definition appears in exactly one unit;
   - only private or internal symbols changed linkage;
   - each unit verifies.

   Release builds do not repeat these integrity checks, following the
   proportionate self-check policy.
6. **Link surface.** `SplitModule` and the bitcode reader and writer are
   expected to be inside the existing `core`/`nativecodegen`/`passes` library
   closure. `scripts/check_llvm_link_surface.py` must confirm that. If a new
   component is needed, ADR 031's link surface needs a recorded amendment.

### Stage C (optional, evidence-gated): parallel late optimization

LLVM cannot run passes on one module from several threads, because the
context's constants and use lists are shared. Parallel optimization therefore
means optimizing units separately. The recommended form keeps everything that
needs the whole program serial, and runs only the optimization half per unit:

- **Serial, whole module:**
  - module simplification, including the CGSCC inliner;
  - internalization;
  - GTI's module transforms (`promoteGuardedDispatchCalls`,
    `specializeBoundedRecursion`, hot and cold splitting,
    `foldInductivePointerLoops`).
- **Per unit:** `buildModuleOptimizationPipeline`, which covers vectorization,
  unrolling and late cleanup.
- **Afterwards:** `reuseCheckedArithmeticResults` and instrumentation then run
  per unit, which is only valid if each is proved function-local or made
  unit-safe.

This reorders GTI's current pipeline. Today the full pipeline runs before the
GTI module transforms and is then repeated. Generated code would change, so
stage C needs runtime benchmark parity evidence and an explicit owner
decision. It is not part of stage B's acceptance.

### Debugging and tools

- **Debug info.** With `-g`, each unit carries a copy of the compile-unit
  metadata for the functions it holds. That gives several DWARF compile units
  for one program, which lldb and gdb handle. Line tables, variable locations,
  and stepping across calls between units must be tested.
- **Tool output.** `--emit-llvm`, `--emit-mir` and diagnostics are unchanged.
  `gti_lsp` never runs the backend and is unaffected.

## Compatibility and migration

- **Default stays one unit.** With `N = 1`, the default until owner sign-off,
  output must be byte-identical to today, so existing caches, determinism tests
  and release artifacts carry on.
- **Cache.** The new object-list schema invalidates object caches once, which
  is acceptable for a project-local cache.
- **No language change.** No source-level change and no language version or
  feature gate. Hidden promoted symbols are a private ABI detail. They are
  never a GTI external ABI promise and are covered by the private
  `executionAbiVersion`.
- **RFC 0005 (symbol mangling, draft).** RFC 0005 treats private
  compiler-generated symbols as numbered internal-linkage names. With
  `N > 1`, some become hidden external symbols visible in object symbol
  tables. The two drafts must agree that these names are deterministic and
  reserved, and whether RFC 0005's private scheme covers them.
- **ADR 031** needs the multi-object handoff recorded, and a link-surface
  amendment only if a new LLVM component turns out to be needed.

## Safety and correctness

- **GTI semantics stay settled upstream.** Every GTI safety property (bounds,
  checked arithmetic, failure propagation, cleanup and drop order, loans) is
  decided in MIR and lowered before the split. Stage B runs no IR
  transformation after splitting, so no proof or check can be dropped by
  partitioning.
- **Remaining risks are at the representation and link level:**
  - a definition duplicated or lost;
  - a promoted symbol colliding with another;
  - lost address identity for a text literal or global;
  - static-initialization or `llvm.global_ctors` ordering across units;
  - thread-local storage access models changing when a variable becomes
    external hidden;
  - unwind tables and personality routines for promoted functions;
  - debug-info inconsistencies.

  Each needs a validation-mode check or a dedicated test (see below).
- **Threading.** Each worker owns its context, module and `TargetMachine`. No
  `Session` state is shared across workers. The shared, read-only inputs are
  the bitcode buffers and target options. LLVM global state, such as
  `cl::opt` values, is read-only after initialization and must not be written
  per unit.
- **Failure.** A failure in any unit fails the whole emission with that unit's
  diagnostic. Remaining workers are joined, not detached. No partial artifact
  is published.
- **Sanitizers.** Address and thread instrumentation insert module
  constructors and global registration. Splitting after instrumentation
  relies on `SplitModule` handling the `appending` `llvm.global_ctors`
  correctly. Until a dedicated test proves that, instrumented builds use
  `N = 1`.

## Performance and resource costs

- **Expected compile-time win.** See [What parallel units could
  save](#what-parallel-units-could-save). On today's corpus, stage B saves at
  most about 2–3% of wall time at either level. On the largest programs, stage
  C could save around 10% at `-O2`. Larger programs, and anything that shrinks
  admission, raise the share that can run in parallel.
- **Overheads to measure:**
  - partitioning;
  - bitcode write and parse per unit, a cost proportional to IR size;
  - duplicated type and constant tables in each context;
  - per-unit `TargetMachine` construction;
  - extra symbols for the linker.

  A single-threaded build at `N > 1` will be slower than at `N = 1`, and that
  cost has to be bounded.
- **Peak memory.** Peak memory rises with the number of units in flight. Each
  holds a parsed module, its machine IR and output buffers. Bound it with
  `--codegen-threads` and measure it.
- **Runtime performance.** Stage B can affect runtime through:
  - calls between units that can no longer use local-linkage conventions
    (functions already marked `fastcc` keep it on both sides);
  - lost machine-level inter-procedural register allocation;
  - code layout.

  Expect small effects, but they must be measured on the benchmark workloads.
  Stage C can also lose late cross-unit optimization.
- **Output size.** Binary size may grow slightly from hidden symbol entries
  and duplicated debug-info headers.

## Alternatives and tradeoffs

1. **Keep the current single-threaded backend.** Zero risk. On the measured
   corpus the cost is at most the 2–8% in the table above.
2. **Reduce serial admission cost first (recommended in parallel with this
   RFC).** Admission is 25–64% of backend time and runs before any LLVM work.
   Halving it saves about as much at `-O0` as stage B's upper bound, with no
   threading, determinism or ABI risk. It is also a precondition for stage B
   to matter: by Amdahl's law, the serial admission share caps what parallel
   code generation can achieve.
3. **Parallel IR construction.** Unit-local `LLVMContext`s from lowering
   onward would parallelize lowering and allow per-unit admission. The large
   refactor (`Layouts`, `Abi`, `DebugInfo`, literal identity) is not justified
   by lowering's 2–5% share.
4. **Split before optimization, with no importing.** This is simple, but it
   loses cross-unit inlining. GTI relies on inlining for checked-arithmetic
   reuse and ownership simplification, so expect runtime regressions. Rejected
   unless stage C's measurements show otherwise.
5. **In-process ThinLTO.** This means module summaries, cross-unit function
   importing and parallel optimization of everything. It has the most
   potential and the most complexity, and GTI's custom module transforms would
   need summary-aware versions. Deferred until stages B and C show the shape
   of the opportunity.
6. **Rely on build-level parallelism only.** `gti build --all` already
   parallelizes across targets. It does nothing for a single large program,
   which is the case whole-program compilation makes common.

The tradeoff the owner would accept with stages A and B is new backend
plumbing:

- a multi-object artifact;
- a cache schema;
- a partitioner;
- a thread budget.

In return, backend time scales with program size and cores, and there is
groundwork for per-unit reuse. The immediate measured gain is modest.

## Unresolved questions

1. **Default unit count, and whether `-O0` ever defaults above one.** The
   `-O0` gain is at most about 2–3% on today's corpus.
2. **Partitioner.** `SplitModule`'s name hashing, or a GTI partitioner that
   follows source modules? The latter is better for locality and for future
   per-unit reuse.
3. **Thread budget under `gti build --all` and `gti test`.** Is a static split
   of `--jobs` enough, or does GTI need a jobserver-style token pool?
4. **Instrumented builds.** Can they split after instrumentation, or must they
   split first and instrument each unit?
5. **Libraries.** Do they stay at one unit permanently, or gain a partial-link
   step (`ld -r`) with an exact exported-symbol check?
6. **Promoted symbol names.** How are they named, and does RFC 0005 cover
   them?
7. **Stage C pipeline order.** Is reordering acceptable, and what runtime
   regression budget applies?
8. **Bitcode round-trip.** Is its cost acceptable, compared with cloning into a
   new context via a GTI-owned IR copier?
9. **Prerequisite or parallel track?** Is admission cost reduction a
   prerequisite for accepting stage B, or a parallel track?

## Implementation plan

Each slice is a separate PR in `lang-gti-official/gti`, tracked from
`docs/plans/implementation-sequence.md` and `docs/plans/performance-tooling.md`.

1. **Backend telemetry (stage A).** Backend phase regions, LLVM pass
   profiling, and a benchmark-script breakdown. No output change.
2. **Admission cost (separate issue, not this RFC).** Profile-driven fixes for
   `Inventory::inspect` and `StaticDispatchProofs` / `containsHierarchyStorage`.
3. **Multi-object plumbing.** `BackendArtifact` object lists,
   `NativeLinkRequest`, a new cache schema and identity, with `N = 1`
   everywhere. Output stays byte-identical. Includes the ADR 031 note.
4. **Partition and parallel code generation (stage B).** `--codegen-units`
   and `--codegen-threads`, still defaulting to `N = 1`, with the
   validation-mode checks and the tests below.
5. **Measurement and default decision.** Corpus, `import std` programs,
   benchmark workloads and large applications, across `N` and `T`. Changing
   the default needs an owner decision recorded here.
6. **Stage C (optional).** A per-unit late optimization pipeline behind its
   own option. Runtime parity evidence first.
7. **Follow-up RFC (optional).** Per-unit object reuse across edits, keyed by
   unit IR digest, once partitions are stable.

## Validation and release criteria

These apply to the implementation PRs. Compiler validation follows the GTI
repository's current policy.

- **Determinism and equivalence:**
  - With `N = 1`, objects and executables are byte-identical to the
    pre-change compiler across the example corpus at `-O0` and `-O2`.
  - With `N = 8`, objects and executables are byte-identical across
    `T = 1, 2, 8`, and across repeated runs.
- **Behavior:**
  - Every example and runtime suite gives the same exit code, output and
    diagnostics at `N = 8` as at `N = 1`, at `-O0` and `-O2`, on macOS arm64
    and Linux.
  - This includes checked-failure, cleanup-ordering, thread, thread-local,
    atomic, native callback and static-initialization programs.
- **Representation checks:**
  - Validation mode detects an injected duplicate or missing definition, and
    an injected linkage change of a non-local symbol.
  - Text-literal address identity holds across units.
  - Promoted names are stable across runs and do not collide.
- **Debugging.** An lldb test sets breakpoints and steps across calls between
  units in a `-g` build.
- **Failure.** A forced LLVM error in one unit fails the build with that
  unit's diagnostic and publishes nothing.
- **Libraries and instrumentation.** Library and embedding builds reject
  `N > 1` with a limitation diagnostic. Instrumented builds either pass their
  existing sanitizer suites at `N > 1` or are pinned to `N = 1`.
- **Performance (acceptance for changing the default):**
  - Report backend and total wall time, CPU time and peak RSS for the corpus,
    `import std`-scale programs and the benchmark workloads, at `-O0` and
    `-O2`, for `N ∈ {1, 4, 8, 16}` and `T ∈ {1, 4, 8}`.
  - Proposed bars, open to owner revision:
    - single-thread overhead at the chosen `N` of at most 5% of backend time;
    - a median backend wall reduction of at least 25% at `T = 4` on programs
      whose backend exceeds 1 s;
    - no runtime benchmark regression outside noise;
    - peak RSS increase of at most 25%.
- **Documentation:**
  - `docs/architecture/backend.md` covers the unit contract;
  - `build-and-driver.md` covers the options, cache schema and thread budget;
  - ADR 031 records the multi-object handoff;
  - `performance-tooling.md` records the measurements.

## Decision record

No design decision yet.

## References

- [`src/compiler/llvm_backend.cpp`][generate]: backend entry. Verification,
  admission, one session, one object.
- [`src/compiler/llvm/session.h`][session] and
  [`session.cpp`][emit]: one context, module and target machine; the full
  optimization and emission sequence this RFC splits.
- [`include/gti/backend.h`][artifact] and
  [`src/driver/build.cpp`][cache]: the single-object artifact and cache
  representation.
- [`docs/architecture/build-and-driver.md`][driver-docs]: reproducible-link
  and serial/parallel byte-equivalence rules, `gti build --all` parallelism,
  and the `--time-trace` phase regions used for the measurements.
- [ADR 031][adr031]: native LLVM backend foundation, object handoff and link
  surface.
- [RFC 0005 draft](https://github.com/lang-gti-official/rfcs/pull/6):
  private symbol naming, which interacts with symbol promotion across units.
- LLVM `SplitModule` (`llvm/Transforms/Utils/SplitModule.h`) and
  `splitCodeGen` (`llvm/CodeGen/ParallelCG.h`): the partitioning and
  parallel code-generation mechanism used by full-LTO code-generation
  partitions.
- rustc codegen units, where the unit count is output-affecting and tuned
  separately from thread count: prior art for the units-versus-threads split
  and the inlining tradeoff.

[generate]: https://github.com/lang-gti-official/gti/blob/12dda2a36ddc61b7aaaf2e27eb5438bb051d4de0/src/compiler/llvm_backend.cpp#L222
[session]: https://github.com/lang-gti-official/gti/blob/12dda2a36ddc61b7aaaf2e27eb5438bb051d4de0/src/compiler/llvm/session.h#L50
[emit]: https://github.com/lang-gti-official/gti/blob/12dda2a36ddc61b7aaaf2e27eb5438bb051d4de0/src/compiler/llvm/session.cpp#L895
[internalize]: https://github.com/lang-gti-official/gti/blob/12dda2a36ddc61b7aaaf2e27eb5438bb051d4de0/src/compiler/llvm/session.cpp#L941
[pipeline]: https://github.com/lang-gti-official/gti/blob/12dda2a36ddc61b7aaaf2e27eb5438bb051d4de0/src/compiler/llvm/session.cpp#L988
[codegen]: https://github.com/lang-gti-official/gti/blob/12dda2a36ddc61b7aaaf2e27eb5438bb051d4de0/src/compiler/llvm/session.cpp#L1039
[literal]: https://github.com/lang-gti-official/gti/blob/12dda2a36ddc61b7aaaf2e27eb5438bb051d4de0/src/compiler/llvm/session.cpp#L568
[artifact]: https://github.com/lang-gti-official/gti/blob/12dda2a36ddc61b7aaaf2e27eb5438bb051d4de0/include/gti/backend.h#L40
[cache]: https://github.com/lang-gti-official/gti/blob/12dda2a36ddc61b7aaaf2e27eb5438bb051d4de0/src/driver/build.cpp#L284
[driver-docs]: https://github.com/lang-gti-official/gti/blob/12dda2a36ddc61b7aaaf2e27eb5438bb051d4de0/docs/architecture/build-and-driver.md
[adr031]: https://github.com/lang-gti-official/gti/blob/12dda2a36ddc61b7aaaf2e27eb5438bb051d4de0/docs/decisions/031-native-llvm-backend-foundation.md
