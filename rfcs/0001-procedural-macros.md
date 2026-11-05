# RFC 0001: Typed procedural macros in three phases

| Field | Value |
| --- | --- |
| Status | draft |
| Authors | @gti-language-official (proposal requested by the owner; drafted with Codex) |
| Created | 2026-11-05 |
| Updated | 2026-11-05 |
| Area | language |
| Proposal | https://github.com/lang-gti-official/rfcs/pull/1 |
| Decision | pending |
| Implementation | [Phase 1 — GTI PR #263](https://github.com/lang-gti-official/gti/pull/263); [Phase 2 — GTI PR #267](https://github.com/lang-gti-official/gti/pull/267) (in progress) |
| Supersedes | none |
| Superseded by | none |

## Summary

Implement the direction in [GTI issue #251](https://github.com/lang-gti-official/gti/issues/251): typed procedural macros declared with `#macro(proc)`, written in GTI, and invoked explicitly with `!`, such as `html!({...})`. The macro runs during compilation, consumes syntax, and returns syntax for ordinary GTI checking. It does not evaluate the caller's runtime expressions while expanding them.

The implementation has **exactly three phases**:

1. Lossless syntax capture, staged name selection, and a typed, hygienic syntax API.
2. Procedural execution through the existing verified-MIR constant engine and checked expression publication.
3. Imported-library integration, diagnostics/tooling/cache completion, and a small HTML-like demonstration.

**The first end-to-end feature acceptance gate is after phase 3. Its centerpiece is a small, separately imported `html!({...})` macro that builds and runs on LLVM.** Phases 1 and 2 have mandatory development checks, but passing them does not constitute feature acceptance. The final gate includes the negative, hygiene, regression, tooling, and cost evidence needed to make that demonstration trustworthy.

This is a design and implementation plan, not an implementation claim. Issue #251 records agreement on the declaration spelling and broad direction. The bounded profile and detailed choices below remain proposed until explicitly accepted.

## Motivation and goals

Allow a GTI library to implement an embedded language, validate its structure at compile time, and generate efficient ordinary GTI. A markup library should diagnose a missing `</div>` itself, while GTI diagnoses an invalid embedded `user.name`, illegal move, or escaping borrow. Neither HTML grammar nor a public library name belongs in compiler semantics.

The first useful outcome is a small node-construction macro, not a complete web framework. An unrelated expression-generating macro must prove that the mechanism works beyond HTML. Existing non-procedural typed macros must retain their current evaluation, hygiene, scoped-return, and cleanup contracts.

### Current foundations and gaps

Source audit baseline: GTI main [`2ec7512ecbc42e736b3d984efbff6304de67be21`](https://github.com/lang-gti-official/gti/commit/2ec7512ecbc42e736b3d984efbff6304de67be21), inspected on 2026-11-05. This proposal does not claim new compiler validation was run.

| Foundation observed at that revision | Reuse and missing work |
| --- | --- |
| [Typed macros](https://github.com/lang-gti-official/gti/blob/2ec7512ecbc42e736b3d984efbff6304de67be21/docs/language/execution.md#typed-statement-macros) already have typed expression parameters, definition/call-site lookup domains, value-result regions, and deterministic expansion limits. | Preserve this contract. Procedural bodies execute during compilation instead of being cloned as runtime statement templates. |
| [The parser](https://github.com/lang-gti-official/gti/blob/2ec7512ecbc42e736b3d984efbff6304de67be21/src/compiler/parser.cpp) parses ordinary macro signatures and function bodies; `FunctionDecl` retains a macro marker. | Add an explicit procedural kind and deferred balanced argument capture. Do not reinterpret existing macro bodies as procedural code. |
| [Semantic macro expansion](https://github.com/lang-gti-official/gti/blob/2ec7512ecbc42e736b3d984efbff6304de67be21/src/compiler/semantic_macro.cpp) and `MacroLookupContext` separate definition and invocation domains. | Extend shared origin, context, expansion-stack, and ownership infrastructure. Do not build a second hygiene system based on string substitution. |
| [The MIR constant executor](https://github.com/lang-gti-official/gti/blob/2ec7512ecbc42e736b3d984efbff6304de67be21/src/compiler/mir_constant_evaluator.cpp) verifies canonical MIR, executes bounded calls/storage, and rejects results retaining transient ownership. | Add a syntax-execution profile and a distinct sealed-syntax publication boundary. Ordinary constant results must keep their existing escape restrictions. |
| [Staged constant limits/reuse](https://github.com/lang-gti-official/gti/blob/2ec7512ecbc42e736b3d984efbff6304de67be21/docs/architecture/semantic-analysis.md#staged-constant-limits-and-reuse) already share request budgets and memoize successful work; executed compile-time panic can carry a library message. | Reuse execution, caching discipline, and failure provenance. Syntax handles, token-span diagnostics, cancellation, and expansion-result caching need explicit additional support. |
| [Macro expansion queries](https://github.com/lang-gti-official/gti/blob/2ec7512ecbc42e736b3d984efbff6304de67be21/include/gti/semantic_model.h) and `gti/inspectMacroExpansion` exist. | Extend their shared frontend representation to procedural expansions; do not introduce a separate LSP expander. |

## Non-goals

The first three phases do not provide declaration/type/pattern expansion, derives, attribute transformations, procedural overload resolution, member macros, same-module procedural invocation, or reflection over the types of arbitrary caller expressions. They do not change non-procedural `#macro` into a matching/repetition language.

They do not provide arbitrary raw-text input, filesystem/network/environment access, native compiler plugins, a JIT, a second compile-time interpreter, or C++ backend feature parity. Persistent expansion caching across compiler processes and a new quotation keyword are not required for this first gate.

The HTML client does not promise full HTML parsing, browser semantics, DOM events, reactivity, or a security-sanitization framework. Those are library goals, not prerequisites for the general procedural-macro mechanism.

## Guide-level design

Proposed declaration in a separately imported GTI module:

```gti
import std.syntax;

// Proposed API and declaration syntax, not available today.
#macro(proc) std::syntax::expr html(std::syntax::tokens input) {
  // Parse the token group in GTI, diagnose invalid markup,
  // and return syntax for ordinary demo node-construction calls.
}
```

This RFC recommends a category-specific `expr` result for the first implementation, rather than the illustrative `tokens` result in issue #251. `expr` proves only that a complete expression was constructed or parsed; it does not prove its type, ownership, effects, or safety. GTI establishes those facts after insertion. The syntax API names are provisional; its required operations and guarantees are specified below.

Proposed user-facing demonstration:

```gti
import demo.html;

// Inside an ordinary function; user.name is a runtime string/view.
auto page = html!({
  <div class="profile">
    <h1>{user.name}</h1>
    <p>{"Welcome!"}</p>
  </div>
});
```

The module exports `html` using GTI's ordinary module rules. Qualified invocation, such as `web::html!({...})` for a macro declared in that namespace, is covered too. The owner selected `!` during phase-1 implementation to make opaque input explicit. No `#expand` or HTML compiler hook is introduced; existing typed macros retain ordinary call spelling.

The macro converts static tags/attributes into literal arguments to ordinary library operations. Each interpolation is parsed as GTI syntax and spliced into the generated expression. The demo library owns its node/text storage; a returned page cannot retain an unchecked borrow into a temporary or the macro executor. Rendering a profile named `Ada & Lin` produces this test result:

```html
<div class="profile"><h1>Ada &amp; Lin</h1><p>Welcome!</p></div>
```

Markup structure is checked while compiling; rendering and copying runtime text are ordinary library work. There is no runtime markup parser.

## Semantic rules

### Initial declaration and invocation profile

- A procedural macro is a namespace-scope declaration with one by-value syntax-group parameter and one `expr` result. Its body is ordinary typed GTI executed in the procedural profile; an additional `consteval` modifier is unnecessary. It is not a function item and cannot be called at runtime.
- The first profile has no macro generics, overloads, packs, defaults, member/operator forms, or multiple syntax arguments. Helpers may use the already supported constant-execution language facilities. Additional shapes are future extensions with explicit staging and argument contracts.
- An eligible invocation names one imported procedural declaration through ordinary unqualified or namespace-qualified lookup and supplies one outer braced group: `name!({...})`. The outer braces delimit the input; their inner balanced groups are retained. Commas inside it are input tokens, not macro argument separators.
- Only imported procedural definitions are callable in this slice. Same-module calls receive a located unsupported-profile diagnostic. This bounds scheduling without making same-module macros a permanent non-goal.
- One qualified name cannot mix ordinary functions, existing typed macros, and procedural macros. A procedural selection must not depend on first type-checking its raw input. Conflicting imports and ambiguous names are diagnosed before expansion. Ordinary local shadowing still applies; no parser heuristic overrides normal lookup.
- A procedural callee must be non-dependent. Calls inside generic code can retain generic caller expressions, but resolving their meaning remains ordinary concrete analysis. A dependent macro name is rejected in this profile; it cannot trigger type-driven interpretation of raw input.

### Capture and lookup timing

The lexer keeps GTI lexical rules. The parser recognizes an explicit `name!({...})` candidate containing a qualified/unqualified name and a balanced braced token group. It never decides from the contents whether this is HTML or ordinary GTI. Source extent, delimiters, token kinds, punctuation adjacency, and trivia boundaries must survive capture.

Semantic lookup requires the name before `!` to select a procedural macro and passes its captured group without evaluating or type-checking embedded expressions. An ordinary callable or a shadowing local cannot acquire procedural behavior through `!`; it receives a diagnostic. Ordinary calls and existing typed macros keep their original parsing and evaluation rules. A procedural declaration called without `!` receives a diagnostic. Regression tests cover ordinary braced calls, shadowing, ambiguity and invalid categories.

Unbalanced GTI delimiters and invalid GTI lexemes remain frontend errors. Balanced but mismatched markup tags are the library's responsibility. In particular, this is token-based syntax, not arbitrary raw HTML: quoted text and GTI comment/string rules apply. Source-loading directives must not run merely because their tokens occur inside the captured group; the capture/source-loading boundary must either retain such spellings inertly or reject them with a located diagnostic. The first profile rejects directives inside captured input and generated output.

### Typed syntax values and hygiene

The required syntax interface consists of:

- Immutable token/group inspection, including delimiters, spelling, adjacency, source spans, and bounded traversal.
- Token/group builders, literal and punctuation construction, definition-context identifier construction, and fresh binding identities with matching reference construction.
- Parsing a caller-owned group into one expression while preserving its lookup/access/generic context. This parses syntax; it does not inspect runtime values or query resolved caller expression types.
- Typed expression splicing into constructed syntax, and sealing exactly one complete expression with no trailing tokens. A builder can provide the first implementation; an ergonomic quotation language can follow later.
- Located failure reporting with a primary span, related spans, and an expansion trace. Library diagnostics cannot forge arbitrary source locations or a compiler diagnostic identity.

Syntax types are compiler-supported capabilities bound to trusted declaration identity, not to public `std::*` spellings. Ordinary library code supplies traversal, markup grammar, and construction policy where it can express the invariants. The public API never exposes mutable compiler AST nodes or unrestricted internal pointers.

Spliced input retains caller context. Constructed identifiers default to definition context; references to a fresh binding use its unforgeable identity, not a specially chosen string. Copying a source span changes diagnostic attribution, not hygiene or access authority. Generated helpers therefore cannot capture same-spelled caller variables, and splices cannot acquire a macro definition's private access rights. Definition-owned helper references retain their legitimate definition context even when the macro is exported.

There is no arbitrary call-site-name fabrication or deliberate export of new public names in this profile. A later extension must define those capabilities explicitly.

### Checking and execution of generated code

The completed `expr` re-enters ordinary semantic analysis at the call site with its retained contexts. Type selection, moves, borrows, lifetimes, access, effects, and cleanup remain normal GTI rules. HIR and verified MIR contain the resulting ordinary program, not an executable procedural-macro call.

The general facility does not promise that an interpolation is evaluated once: the generated program determines whether and how often it is used. The HTML library's own contract is stronger: each interpolation appears exactly once, evaluated in document order using GTI's normal left-to-right rules. It must not silently stringify arbitrary types or duplicate consumption of an owner.

No syntax constructor confers unsafe authority. The first profile rejects synthesized unsafe blocks/annotations and generated directives; a caller-written explicit unsafe expression retains its original context and ordinary obligations. An emitted call requiring unsafe authorization is still checked normally. Expansion inspection and diagnostics identify both definition and invocation origins.

## Compiler and tooling design

### Ownership of the pipeline

| Layer | Responsibility |
| --- | --- |
| Source loader / lexer / parser | Preserve source and balanced groups, distinguish the procedural declaration kind, and parse generated expression syntax. No embedded-language grammar or semantic guessing. |
| Semantics | Resolve macro identity/imports, type-check macro implementations, schedule staged execution, retain hygiene contexts, and check the resulting ordinary expression in caller flow. |
| Staged HIR/MIR boundary | Lower completed macro/helper closures to canonical verified MIR at the point expansion is needed. Do not wait for whole-program HIR/MIR to exist. |
| Existing MIR executor | Execute GTI operations under a procedural profile with bounded syntax capabilities, shared budgets, cancellation, and located failure. No new AST execution path. |
| Frontend snapshot / expansion records | Own the sealed syntax graph and provenance through semantic analysis, HIR lowering, diagnostics, and tooling queries. |
| LLVM | Compile the checked ordinary result. It neither implements HTML nor reconstructs macro meaning. |
| Driver / LSP | Supply the same source/configuration/limits, track dependencies, and consume shared frontend expansion and diagnostic results. |

### Scheduling, storage, and publication

Resolve imported module declarations first, then stage the selected procedural body and its executable helper closure lazily. Track pending/active/completed expansion and staging requests by declaration and input/context identity. Detect recursive definition dependencies and repeated expansion cycles before unbounded work. Nested invocations in generated expressions re-enter the same scheduler and share the outer request's limits. Import cycles follow the existing module rules; a cycle requiring an unfinished macro result is a staged dependency error.

Reuse the engine behind `evaluateMirConstantFunction`, but introduce an explicit procedural request/result profile. The present executor imports/publishes persistent constant values and rejects escaping transient storage. Syntax output cannot be obtained by disabling those checks for ordinary constants.

A procedural invocation has a bounded syntax arena associated with its frontend request. Handles carry arena/session and generation identity and are validated on every capability boundary. Syntax may be held in local/helper values under the procedural type rules, but cannot become runtime storage, a persisted ordinary constant, a process-global value, or an arbitrary pointer.

On success, seal and retain the result's reachable syntax/provenance graph in the frontend snapshot before executor teardown. No returned syntax may point into freed interpreter allocations, a temporary analysis worker, or an older editor snapshot. Aborted requests publish neither partial syntax nor partial semantic facts. Ordinary temporary ownership and cleanup inside the executor retain their existing rules. This publication boundary needs explicit verifier and lifetime tests.

The interpreter runs inside the build host process, but GTI target-dependent integer/layout facts come from the selected target profile. No host-native proc-macro shared library is built. Host paths, wall clock, randomness, environment, filesystem, network, FFI, runtime-only calls, and threads are unavailable in the first procedural profile. Read-only selected-target/configuration facts must be explicit inputs to the request, not accidental ambient dependencies.

### Limits, cancellation, and reuse

Reuse `CompileLimits`, the shared staged constant work budget, and macro depth/expansion accounting. Add explicit syntax-node/storage and output-token/byte limits, including generated group depth and diagnostic-volume bounds. Charge bulk parsing, copying, string construction, and traversal by logical work/size rather than treating an arbitrarily large intrinsic operation as one step. A nested macro or cache hit cannot reset the outer budget.

Proposed starting defaults for the new syntax-specific controls are 65,536 live arena nodes, 1 MiB of retained token spelling/trivia, 65,536 emitted tokens, and 1 MiB of emitted spelling per outer invocation. These are proposed engineering limits, not measured capacities or new language guarantees. Phase 2 must measure and document suitable defaults/minimums through GTI's existing limits contract before the final gate; lowering a limit must still give a deterministic named-limit diagnostic. Count all allocated arena nodes until reclamation, including nodes not reachable from the eventual result; discarded construction still consumes work budget. Existing constant heap limits are not silently repurposed as syntax-arena accounting.

Cancellation is checked during interpretation and bulk syntax operations. LSP cancellation produces a cancelled request, never a stale diagnostic or successful truncated expansion. Resource-limit failures are located diagnostics; neither limits nor runtime-only failures retry through the legacy AST evaluator. Internal invariant failure remains a compiler defect, distinct from a library-authored rejection.

Begin with successful expansion reuse scoped to one immutable frontend analysis snapshot, following the existing constant-cache discipline. The key includes macro declaration/body and transitive helper/module identities, compiler/syntax-profile version, target/configuration, input token structure and trivia where observable, hygiene/lexical/generic context, and limits. Cache hits replay recorded logical cost and diagnostics with correct locations and instantiate fresh generated binding identities for each invocation; they must not share a mutable expansion tree or capture another call's scope. Do not cache cancellation, errors, or half-built results.

Across edits, discard or precisely invalidate entries; a whole-snapshot discard is an acceptable first implementation. Existing build-cache dependencies must include procedural definitions and their helper/import closure, so changing a macro library invalidates consumers. Cross-process syntax serialization is deferred; raw arena handles are never cache artifacts.

### Diagnostics and editor behavior

A macro-authored error reports a library message at a validated input span, with optional related spans and nested invocation/definition traces. A missing closing tag should point to end-of-input or the relevant boundary and relate the opening tag. A mismatched closing tag should point to that closing name and relate the opener. Malformed generated GTI reports the macro's construction/definition origin plus its invocation, rather than pretending generated text was written by the caller.

CLI and LSP use the same expansion result. Extend `gti/inspectMacroExpansion` and existing semantic queries instead of adding another evaluator. Inspection exposes generated source with hygiene/provenance annotations; pretty-printed text alone is not a round-trippable representation of hygienic syntax.

The formatter preserves opaque input groups without applying GTI expression formatting inside the embedded language. Tree-sitter and editor syntax recognize `#macro(proc)` and the group boundary, while completion/hover/navigation for successfully parsed splices use shared source mappings. Incomplete groups must recover enough to continue the editor's snapshot, avoid repeated expansion work, and suppress stale output after edits/cancellation. No HTML-specific frontend or LSP grammar is required.

## Compatibility and migration

Non-procedural typed macros keep their current signatures, overload rules, lazy expression forcing, scoped returns, caller/definition hygiene, tracked-caller behavior, and cleanup. Preserve their existing tests, including fresh callable identity and expression-text provenance. The new syntax is additive and does not redefine `#define`, assertions, or ordinary function argument evaluation.

[ADR 030](https://github.com/lang-gti-official/gti/blob/2ec7512ecbc42e736b3d984efbff6304de67be21/docs/decisions/030-deferred-statement-helpers.md) remains the authority for non-procedural templates. This RFC proposes an additional explicitly selected mode; adoption should record that distinction in the ADR and update implemented language/architecture documentation as the feature lands. Historical plans remain in GTI, linked to this RFC.

New executable capability is LLVM-first. C++ feature parity is not an acceptance requirement. Unsupported C++ handling must remain honest and must not weaken LLVM checking or execution coverage. No release availability follows merely from merging this RFC or an intermediate phase.

## Safety and correctness

The principal proof obligations are:

1. Name selection cannot change evaluation policy by guessing the input grammar or by type-probing a runtime interpolation.
2. Context-bearing syntax cannot forge access, capture names accidentally, cross snapshot boundaries, or survive executor teardown through dangling storage.
3. A successful parse is not a safety proof: generated code undergoes ordinary semantic, ownership, MIR verification, and LLVM execution checks.
4. Bounded expansion, interpreter work, allocation, output, diagnostics, and cancellation apply transitively, including helper calls, nested macros, and cache replay.
5. A macro cannot acquire untracked host effects or inject source-loading directives or new unsafe authority.
6. Errors, cancellation, and invalid output publish no partial program or stale editor result.

The HTML renderer escapes text and attribute values using ordinary library code; the demo tests `&`, `<`, `>`, and quote handling. This is not a claim that the demonstration is a complete browser-content sanitizer. Macro structural validation alone never justifies an unchecked runtime operation.

## Performance and resource costs

Expected successful-path costs are compile-time token traversal/construction plus normal checking/lowering of the generated expression. There must be no runtime macro interpreter, syntax arena, or markup parser in the produced program. Runtime operations and allocations belong to the emitted node/text API and should match equivalent handwritten calls.

Record cold and warm compilation time, expansion/interpreter work, peak memory, generated IR/object size, runtime, and allocations. Compare the HTML expansion with handwritten calls using the same data structure, ownership, escaping, and error contract. Measure an unrelated macro too. Use 1, 16, and 256 invocations and small/medium/larger trees (for example 8, 32, and 128 nodes) to expose repeated staging, whole-model copying, quadratic syntax rebuilding, and unbounded retained roots.

Warm reuse must preserve diagnostics and logical budget charges. Observe cross-platform host differences without confusing them with target semantics. Report measurements and variance; do not claim a speedup in this RFC. A material runtime regression against the equivalent handwritten contract fails acceptance unless the owner explicitly accepts the measured tradeoff. Compile-time and memory growth must be explained and bounded before the gate; raising limits is not a substitute for fixing pathological work.

## Alternatives and tradeoffs

- **Extend existing typed templates only:** retains familiar semantics but cannot parse an arbitrary captured token language or run a source-defined syntax generator. Keep them for their existing lazy-expression use cases.
- **Use strings as input/output:** superficially simpler, but loses reliable context, spans, token boundaries, and safe splicing. Text reparsing with caller authority is not the proposed design.
- **Run native proc-macro plugins:** can reuse broad host libraries, but introduces host ABI, bootstrap/cross-compilation, isolation, reproducibility, and crash boundaries. Reusing verified MIR is the chosen first direction.
- **Create a new compile-time AST interpreter:** short-term convenience would duplicate GTI execution rules. Extend the existing staged engine and its explicit capability profile instead.
- **Return unconstrained tokens initially:** permits more expansion positions, but broadens grammar/staging/injection rules. The proposed `expr` result gives a useful end-to-end slice and leaves later categories explicit.
- **Keep ordinary invocation spelling:** was the initial direction in #251. The owner revised it on 2026-11-05 to use `!` for procedural macros. Explicit capture avoids reparsing ordinary calls and lets source loading reject directives only inside procedural input. Existing typed macros are unchanged.
- **Implement HTML in the compiler:** might make one demo easy but fails the general facility requirement. The unrelated macro and library-owned grammar are mandatory.

## Unresolved questions

These are design decisions to settle during review or the named phase, not claims of missing implementation already being acceptable:

- Final public syntax type/function names and the source-library versus trusted-capability split. The minimal builder/parse/splice/span contract above is required; phase 1 must make its signatures and failure behavior concrete.
- Whether reviewers prefer the proposed `tokens -> expr` profile or a different category-checked boundary. Unrestricted token publication is not an implicit fallback.
- Source-loader interception is resolved by the explicit `name!({...})` boundary: inspect raw lexical groups before processing directives or replaying a processed unit. Reject directives/imports inside the group before publishing effects. Ordinary-call directive behavior remains unchanged; malformed-group recovery and cache replay still require tests.
- Concrete limit names, defaults/minimums, and cancellation granularity, informed by phase-2 measurements. All required limit dimensions and deterministic failure behavior remain mandatory.
- The smallest representation for the demonstration's owned node tree using currently supported GTI libraries. Keep its contract equivalent to the handwritten comparison; do not add a nominal compiler exception to accommodate it.

Same-module invocation, explicit exported-name hygiene, declaration/type/pattern output, richer parameters, reflection-assisted stages, persistent caches, derives, and attribute transformations remain later goals. Each needs a separate reviewed extension of these contracts; none is required to quietly leak into the first three phases.

## Implementation plan

The phases are sequential dependencies, not three separate feature acceptance gates. Normal focused tests, review, PR integration, and required CI apply throughout. Intermediate work can land with an explicit incomplete status; it must not be advertised as an accepted procedural-macro feature before the gate after phase 3.

### Phase 1 — Syntax capture and typed construction

**Outcome:** the frontend can represent and select an imported procedural declaration and its opaque input without consuming embedded text as ordinary GTI first; the typed syntax API has a concrete, tested ownership/hygiene contract.

Work:

1. Add procedural declaration identity without changing existing typed-macro representation/behavior by accident. Define initial signature restrictions and ambiguity/shadowing diagnostics.
2. Introduce lossless balanced groups and explicit procedural-call candidates at the loader/lexer/parser boundary. Preserve ordinary-call behavior, lexical rules, directives rejection, incomplete-input recovery, and source extents.
3. Implement immutable syntax storage, typed cursors/builders, expression parsing/splicing, definition-context/fresh identifiers, and validated diagnostic spans. Bind intrinsic capabilities by trusted identity.
4. Extend shared macro context/provenance and expansion ownership structures; document syntax-arena lifetimes and the result-sealing interface for phase 2.
5. Add declaration/group handling to formatter, Tree-sitter, and editor syntax recognition, with opaque-content preservation.

**Development evidence:** parser/capture round trips; nested delimiters, punctuation/trivia, missing delimiters, directives, wrong arity/category, name mixtures/shadowing, ordinary braced-call regressions; context/splice isolation and stale-handle rejection; formatter/Tree-sitter recovery. Existing typed-macro parser and syntax tests remain green. Compiler harness construction of syntax is test scaffolding, not proof of executable procedural macros.

**Dependency handed to phase 2:** checked declaration and syntax types, stable invocation contexts, and a sealed result/provenance contract. There is no end-user feature acceptance gate here.

### Phase 2 — Verified-MIR execution and checked expansion

**Outcome:** an imported GTI procedural body can execute with syntax values and publish one expression that ordinary semantics, HIR/MIR, and LLVM can consume.

Work:

1. Stage completed procedural/helper closures using the existing constant-execution architecture at the pre-expression-checking query point. Add the explicit procedural verifier/executor profile, not an AST fallback or host plugin.
2. Implement bounded syntax intrinsics and temporary storage, helper calls, deterministic work/storage/output charges, cancellation, and located library failures.
3. Implement atomic sealing/retention of result syntax before worker teardown; preserve ordinary constant publication restrictions and normal generated-code checking.
4. Add cycle tracking and nested expansion scheduling with a shared outer budget. Establish definition/call-site/fresh-binding hygiene through generated locals, caller splices, and generic caller contexts.
5. Exercise target-profile inputs independently of the host and implement the per-snapshot cache-key/cost-replay contract. No persistent raw handles.

**Development evidence:** source-defined identity and construction macros; a non-HTML evaluate-once expression macro with a fresh local; imported helpers and nested expansion; both LLVM optimization modes; positive ownership/cleanup and negative type/access/borrow cases; malformed output, recursion/cycles, exhausted limits, forbidden effects, cancellation, and retained-result lifetime tests. Inspect ordinary HIR/MIR and prove no procedural call survives to runtime. These are implementation checks, not the first feature acceptance gate.

**Dependency handed to phase 3:** a working general execution/publication path with reproducible diagnostics and bounded behavior. Unsupported prerequisites must be repaired here, not bypassed for HTML.

### Phase 3 — Complete the library workflow and demonstrate HTML

**Outcome:** a separately imported GTI library implements the small HTML-like macro, and CLI/editor/build workflows use the same completed general facility.

Work:

1. Finish exported-module packaging/import scheduling, helper dependency invalidation, cold/warm expansion consistency, and target/configuration identity. Test an installed toolchain consuming the external macro library.
2. Complete nested source mappings, library-authored primary/related diagnostics, expansion inspection, embedded-expression editor queries, incomplete input recovery, and cancellation/stale-snapshot handling.
3. Implement the HTML grammar and node-construction/rendering client in ordinary GTI. Register a runnable example and its applicable corpus/census evidence in the implementation repository.
4. Retain the unrelated evaluate-once macro as a public-facing example/test of generality. Finish non-procedural macro regressions and generated ownership/cleanup cases.
5. Record handwritten-equivalent runtime/allocation/code-size and compile-time/memory scaling measurements; update implemented language, architecture, diagnostics, syntax-library, and editor documentation.

**First acceptance gate:** perform G1 below only after all three phases are integrated into one exact candidate. The small `html!({...})` demonstration is the visible acceptance result; a toy happy-path expansion alone does not satisfy it.

### Small HTML demonstration scope

The library accepts one root element, nested elements, explicit self-closing elements, quoted literal text, GTI-expression children, and string/expression attribute values. Names are simple ASCII word spellings, including keyword tokens such as `class` when used as markup names; the lexer must not be changed to make them identifiers globally. Raw unquoted text, comments/entities, hyphenated names, spreads, and framework features are outside this example's grammar.

A compact library grammar is:

```text
page      := element
name      := a GTI identifier-or-keyword token with an allowed ASCII word spelling
element   := '<' name attribute* '>' child* '</' same-name '>'
           | '<' name attribute* '/>'
attribute := name '=' (string-literal | '{' gti-expression '}')
child     := element | string-literal | '{' gti-expression '}'
```

Whitespace/trivia is preserved by capture but ignored between markup tokens by this library. String content is retained. GTI lexing remains authoritative, so this grammar does not promise HTML comment or arbitrary raw-text lexing. The macro validates structure and emits ordinary constructors/helpers. GTI checks interpolation types through those helpers. The demo accepts text values and node children according to explicit library overloads; an unsupported value is a normal type error, not implicit stringification.

## Validation and release criteria

### G1 — First feature acceptance, after phase 3

Use one exact combined candidate with an optimized host compiler and record commit, target, commands, results, logs, and cost data. The gate is conjunctive:

| Evidence | Required result |
| --- | --- |
| Small imported HTML client | The guide example compiles and executes on LLVM at O0 and O3 on macOS arm64 and Linux x64, constructing and rendering the expected node tree; installed-toolchain import works. |
| Markup failures | Missing/mismatched closing tags, invalid attributes/children, and extra roots reject with library-authored messages at useful primary/related spans. Unbalanced GTI delimiters retain frontend recovery. |
| Ordinary GTI checking | Unknown `user.name`, unsupported child type, private access, repeated owner consumption, and escaping borrows are rejected by their normal rules at mapped origins. Valid moves, temporaries, and cleanup retain correct behavior. |
| Evaluation and hygiene | Side-effect counters prove each HTML interpolation runs once in document order. Same-spelled caller/definition/generated locals do not capture each other. Imported private helper references and caller access remain in their own domains. |
| Generality | A separately defined non-HTML expression macro evaluates its input once through a fresh generated local and returns its computed result. No HTML or public library spelling selects compiler behavior. |
| Existing macro behavior | Current typed-macro lazy forcing, exact arguments, scoped return, fresh callable, written-origin, resource-limit, and cleanup tests remain passing. |
| Failure containment | Malformed output, wrong syntax category, cycles, excessive nesting/work/storage/output, forbidden host effects, cancellation, and stale/cross-session handles fail without partial publication, ICE, or unbounded work. |
| Workflow and tooling | Nested/imported expansions, qualified calls, generic caller expressions, CLI/LSP diagnostic parity, inspection, formatting preservation, syntax recovery, and stale-editor-result rejection are covered. |
| Reuse and target identity | Change the macro body, transitive helper, input/trivia, caller context, target, configuration, and limits: no stale output or hygiene reuse. Cold and warm runs agree and charge consistent budgets. |
| Runtime and resource cost | No runtime markup parser or procedural engine in the result; allocations and operations match the equivalent handwritten construction. Report runtime, code size, compile time, and peak memory across the stated scaling fixtures; resolve pathological growth and material runtime regressions. |
| Documentation and example | Runnable HTML and unrelated examples, syntax-library contract, implemented semantics/architecture, diagnostic provenance, limits, and editor guidance match the tested slice. |

Tests should extend existing owners where appropriate (`macro_result_parser`, `macro_values_semantic_ir`, `macro_values_runtime`, `macro_result_failures`, `macro_fresh_callables`, `macro_fresh_callable_runtime`, `macro_expansion_queries`, and `macro_neovim_syntax`) and register focused procedural capture, execution, diagnostic, hygiene, cache, cancellation, and library-consumer cases. Proposed new test groups are implementation work, not claims that those tests already exist.

Contributors run the reproducer/new cases, owning/cross-phase/tooling checks, `compiler_pipeline`, native smoke, and relevant platform/performance checks under GTI's current workflow. Integration CI and post-integration full validation retain their responsibilities; do not run redundant complete local suites to finish each phase. C++ parity is not a new-feature gate. Passing G1 supplies implementation-acceptance evidence for this bounded feature, subject to the owner's decision; release availability still requires the relevant release pipeline. No preview-channel publication is part of this plan.

## Decision record

- 2026-11-05: the owner explicitly requested implementation of phase 2. GTI PR #267 implements the MIR procedural request profile, source `std::syntax` operations, sealed expression checking, shared limits and snapshot-local successful reuse. Focused validation passed on the clean phase-2 candidate `31e577bcb5c6bbe1979a7eeac43c28c6b4272de2`; PR #267 is proceeding through normal required CI and merge-queue integration. This does not claim the phase-3 HTML gate has passed. The concrete API adds a checked `keyword` builder alongside literal/punctuation/identifier construction, and names validated spans `location` to avoid colliding with the `span` type. Initial configurable defaults are 65,536 nodes, 1,048,576 cumulative spelling bytes, 65,536 cumulative tokens and 256 group levels, plus the existing shared constant/macro limits. On macOS arm64 with LLVM 23, 40 focused subsystem checks, `compiler_pipeline`, and native scalar/ownership smoke at O0/O3 passed (remote run `run-c2218ecedcf6418abb90c75d48408e57`; full commands/evidence are recorded on PR #267). The source examples cover evaluate-once side effects, move-only cleanup, constexpr initializers and default arguments; owning tests also cover distinct same-spelled fresh bindings, target selection, recursion, cancellation and source syntax operations. An LLVM O3 identity-macro loop and its handwritten equivalent both produced 264 text bytes and 16,904-byte executables with no syntax/allocation operations in MIR. Nine interleaved samples gave medians 95.952 / 95.966 ms; three compiler samples gave medians 90.264 / 88.288 ms and peak RSS 98,844,672 / 99,401,728 bytes (direct / macro). No speedup is claimed. Shared Linux hosts lack the new LLVM 23 pin, so the required cross-platform PR/queue gate remains mandatory; earlier Linux LLVM22 development evidence is not current-pin evidence. Broader library/HTML scaling and final feature acceptance remain phase 3.

- 2026-11-05: the owner authorized phase 1 and explicitly selected `name!({...})` for procedural invocation, retaining existing typed macro calls. This supersedes the earlier ordinary-call spelling from #251. Phase 1 focused evidence and its implementation are recorded in GTI PR #263; final feature acceptance remains after phase 3.

- 2026-11-05: the owner requested a three-phase implementation plan in this repository, with the first acceptance gate after phase 3 centered on a small `html!({...})` demonstration.
- Issue #251 records agreement on `#macro(proc)`, typed syntax, ordinary calls, and preservation of existing typed macros. It leaves the syntax API and staging details open.
- The owner authorized phases 1 and 2 of this bounded expression-only, single-group, imported-definition design. The overall feature remains pending its first acceptance gate after phase 3; the proposal status remains `draft` until that explicit decision.

## References

- [GTI issue #251: typed procedural macros](https://github.com/lang-gti-official/gti/issues/251) — motivating proposal and agreed direction.
- [Typed macro semantics](https://github.com/lang-gti-official/gti/blob/2ec7512ecbc42e736b3d984efbff6304de67be21/docs/language/execution.md#typed-statement-macros) and [ADR 030](https://github.com/lang-gti-official/gti/blob/2ec7512ecbc42e736b3d984efbff6304de67be21/docs/decisions/030-deferred-statement-helpers.md) — existing behavior that must remain intact.
- [L-CONST-01](https://github.com/lang-gti-official/gti/blob/2ec7512ecbc42e736b3d984efbff6304de67be21/docs/plans/implementation-sequence.md#l-const-01-remaining-bounded-compile-time-programming) and [staged limits/reuse](https://github.com/lang-gti-official/gti/blob/2ec7512ecbc42e736b3d984efbff6304de67be21/docs/architecture/semantic-analysis.md#staged-constant-limits-and-reuse) — execution staging, existing facilities, limits, and remaining prerequisites.
- [Source loader](https://github.com/lang-gti-official/gti/blob/2ec7512ecbc42e736b3d984efbff6304de67be21/src/compiler/source_loader.cpp) — configuration/import processing precedes ordinary parsing and must be accounted for by capture.
- [Frontend architecture](https://github.com/lang-gti-official/gti/blob/2ec7512ecbc42e736b3d984efbff6304de67be21/docs/architecture/frontend.md), [parser](https://github.com/lang-gti-official/gti/blob/2ec7512ecbc42e736b3d984efbff6304de67be21/src/compiler/parser.cpp), and [token representation](https://github.com/lang-gti-official/gti/blob/2ec7512ecbc42e736b3d984efbff6304de67be21/include/gti/token.h) — capture and provenance integration points.
- [Semantic macro engine](https://github.com/lang-gti-official/gti/blob/2ec7512ecbc42e736b3d984efbff6304de67be21/src/compiler/semantic_macro.cpp), [lookup contexts](https://github.com/lang-gti-official/gti/blob/2ec7512ecbc42e736b3d984efbff6304de67be21/src/compiler/semantic_analyzer_impl.h), and [shared expansion queries](https://github.com/lang-gti-official/gti/blob/2ec7512ecbc42e736b3d984efbff6304de67be21/include/gti/semantic_model.h) — hygiene, ownership, and tooling foundations.
- [MIR constant executor](https://github.com/lang-gti-official/gti/blob/2ec7512ecbc42e736b3d984efbff6304de67be21/src/compiler/mir_constant_evaluator.cpp) and [its request/result interface](https://github.com/lang-gti-official/gti/blob/2ec7512ecbc42e736b3d984efbff6304de67be21/include/gti/mir_constant_evaluator.h) — verified execution and persistent-result restrictions.
- [Issue #174](https://github.com/lang-gti-official/gti/issues/174) and [issue #175](https://github.com/lang-gti-official/gti/issues/175) — related constant-failure and consistency work; the audited L-CONST record describes the delivered foundation, not syntax-span procedural diagnostics.
- [RFC contribution and decision rules](../CONTRIBUTING.md) — draft publication, explicit acceptance, and implementation evidence.
