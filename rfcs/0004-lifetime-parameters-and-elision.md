# RFC 0004: Lifetime parameters with inference and elision

| Field | Value |
| --- | --- |
| Status | draft |
| Authors | @gti-language-official (with Codex) |
| Created | 2026-11-06 |
| Updated | 2026-11-06 |
| Area | language |
| Proposal | https://github.com/lang-gti-official/rfcs/pull/5 |
| Decision | pending |
| Implementation | https://github.com/lang-gti-official/gti/pull/302 (draft, in progress) |
| Supersedes | none |
| Superseded by | none |

## Summary

Add lifetime parameters to GTI's existing generic declaration syntax:
`lifetime a`, references written `T&<a>` and `mut T&<a>`, and borrowed types
such as `std::string_view<a>`. Infer lifetime arguments in ordinary usage and
elide predictable relationships in declarations. Explicit names remain available
when an API needs to state a relationship that inference cannot reliably expose.

The target experience is that people using maps, vectors, views and iterators
usually write no lifetime parameters. Authors of borrowing abstractions can
express reusable contracts with one type-system mechanism, rather than a growing
collection of attributes for different directions of borrow flow. Named
lifetimes are compile-time constraints, not runtime values or ownership handles.

This RFC is the prerequisite design for [RFC 0003: borrowed container
elements](0003-borrowed-container-elements.md). That RFC owns dynamic storage
admission and container behavior. This RFC owns notation, inference, elision,
compatibility of lifetime-bearing types and declaration contracts. It does not
depend on RFC 0003: references and ordinary borrowed records provide independent
acceptance cases. Container examples require both proposals.

**Status:** the design record remains a draft. After requesting this proposal,
the owner explicitly requested end-to-end implementation with two subagents;
that work is tracked in the draft implementation PR above. Remaining semantic
and compatibility obligations are still being resolved. Neither this document
nor the implementation PR claims that the feature is complete or released.

## Motivation and goals

GTI already has checked references, field-wise origin tracking in borrowed
aggregates, owner-tracked text views, inferred body summaries and explicit
`[[borrowed_from(owner)]]` / `[[borrowed_from(this)]]` return contracts. These are
useful foundations, but current storage and declaration boundaries do not provide
a general way to express relationships among nested borrowed types.

Implementation evidence in the inspected GTI snapshot
[`adbe89e5644414939707f8de4069fa2aca7a0baf`](https://github.com/lang-gti-official/gti/tree/adbe89e5644414939707f8de4069fa2aca7a0baf):

- [Ownership rules](https://github.com/lang-gti-official/gti/blob/adbe89e5644414939707f8de4069fa2aca7a0baf/docs/language/ownership-and-lifetimes.md)
  explicitly introduce no source lifetime parameters. They support independent
  reference-field origins while rejecting several dependency-changing and
  borrowed-array/storage cases.
- [Borrow-origin syntax tests](https://github.com/lang-gti-official/gti/blob/adbe89e5644414939707f8de4069fa2aca7a0baf/tests/borrow_origin_syntax_tests.cpp)
  exercise the existing attributes, including formatter and query consumers.
- [Storage constraints](https://github.com/lang-gti-official/gti/blob/adbe89e5644414939707f8de4069fa2aca7a0baf/stdlib/std/detail/memory_core.gti)
  require `is_borrow_free<T>()`; raw construction in
  [semantic ownership analysis](https://github.com/lang-gti-official/gti/blob/adbe89e5644414939707f8de4069fa2aca7a0baf/src/compiler/semantic_ownership_analysis.cpp)
  rejects checked borrowed state without a tracked destination owner.
- [Borrowed service aggregates](https://github.com/lang-gti-official/gti/blob/adbe89e5644414939707f8de4069fa2aca7a0baf/examples/109-borrowed-aggregates.gti)
  demonstrate existing useful annotation-free composition to preserve.

These are source/document observations, not fresh compiler execution evidence.
RFC 0003 separately records its dated probes; this proposal does not relabel
those probes as validation of lifetime syntax.

User-facing outcomes:

1. A text index can retain views in a collection without copying the characters,
   using ordinary declarations and insertion calls (with RFC 0003).
2. A parser/context/view author can distinguish borrows from independent inputs.
3. A returned view or collection can state which input lifetimes it requires.
4. A concept, virtual operation or callable contract can express the same
   relationships as a concrete function, without needing the callee's body.
5. A compiled interface can carry a stable borrow contract. This supports future
   separate compilation but does not itself implement a compiled-library format.
6. Ordinary existing reference code remains concise, with useful diagnostics
   when a relationship needs a name.

Success includes an ergonomics corpus proving where annotations disappear, not
merely parser support for the explicit spelling. No percentage of annotation-free
programs is claimed before that corpus exists.

## Non-goals

- Runtime lifetime checks, reference counting, automatic owner lifetime extension,
  new allocation policy, or an implicit owning conversion of borrowed views.
- Making references reseatable, nullable or regular assignable container values.
  `T&` keeps its current reference semantics. Borrow-carrying value types remain
  distinct from bare reference types.
- Automatically permitting self-reference, arbitrary borrowed globals, escaping
  captures, cross-thread transfer or native-language lifetime inference. Their
  existing ownership and capability conditions remain in force.
- Admitting all borrowed storage shapes by removing a trait restriction. RFC 0003
  owns its shared-element slice; exclusive elements need their own storage proof.
- Whole-program inference as a requirement for type checking a public API.
- C++ backend feature parity, stable cross-version ABI, or a new release process.

## Guide-level design

All lifetime-parameter syntax below is proposed. Some short forms already work
in bounded cases today; the new explanation of their general behavior is a draft.
Explicit and elided versions of the same function are alternative spellings,
not two overloads to declare together. Snippets omit unrelated setup.

### Reference and generic spelling

| Spelling | Meaning |
| --- | --- |
| `T&` | Read-only reference with a lifetime supplied by context/elision |
| `T&<a>` | Read-only reference valid for region `a` |
| `mut T&<a>` | Exclusive mutable reference valid for region `a` |
| `Borrowed<T, a>` | A borrowing type instantiated with lifetime `a` |
| `std::string_view<a>` | Text whose borrowed characters are valid for `a` |
| `T&<_>` | Explicitly request the same contextual inference/elision as omission |
| `T&<static>` | Reference backed by storage guaranteed valid for the static region |

A lifetime is an interval/set of program points over which validity is required,
not a duration in seconds, an object identity, a runtime token or a command to
keep an owner alive. An annotation cannot make a local or temporary live longer.

```gti
int&<a> identity<lifetime a>(int&<a> value) {
  return value;
}

// Signature elision supplies the same relationship.
int& identity(int& value) {
  return value;
}
```

Generic parameters remain beside the declaration's name. Their scope includes
the entire signature, including a return type textually before the binder.

### Several possible inputs

```gti
int&<a> choose<lifetime a>(bool take_left, int&<a> left, int&<a> right) {
  if (take_left) { return left; }
  return right;
}

int first = 10;
int second = 20;
int& selected = choose(true, first, second);  // no lifetime arguments
```

Both inputs must be valid for the required region `a`; their owners may have
different lifetimes. The declaration permits the result to refer to either
input. A caller cannot assume it always refers to `left` because of today's
implementation or a constant-looking argument.

A stable declaration with two unrelated input lifetimes cannot omit an ambiguous
result relationship. It must say which input it follows, or introduce the common
region above. Lifetimes do not promise that every ambiguous case will be inferred.

### Borrowing types

```gti
struct Borrowed<T, lifetime a> {
  T&<a> value;
};

struct ParserContext<lifetime input, lifetime config> {
  std::string_view<input> source;
  Config&<config> settings;
};
```

`ParserContext` can return a copy of its source view tied to `input` without
unnecessarily tying that view to `config` or to the context object's storage.
Returning a reference to the *field object* still requires the context itself.

Local construction can infer lifetime arguments:

```gti
int number = 42;
Borrowed<int> value{number};
```

For simple record declarations, omitted field lifetimes are proposed anonymous
lifetime parameters, determined by field structure rather than constructors'
bodies. This preserves an approachable version of existing carrier syntax:

```gti
struct PairView {
  int& first;
  int& second;
};  // two independent anonymous lifetime parameters, not one shared parameter
```

Names are required to equate those parameters or reference them explicitly in
an API. The precise migration of recursive/aliased declarations is an acceptance
question, not permission for unbounded hidden-parameter expansion.

### Borrowed collections and insertion APIs

Together with RFC 0003:

```gti
std::string alice{"Alice"};
std::string bob{"Bob"};
mut std::unordered_map<std::string_view, int> scores{};
scores.insert(alice.view(), 10);
scores.insert(bob.view(), 20);
std::println(scores.at("Alice"));
```

A stable helper declaration connects stored and incoming lifetimes:

```gti
void add_score<lifetime keys>(
    mut std::unordered_map<std::string_view<keys>, int>& scores,
    std::string_view<keys> name,
    int score) {
  scores.insert(name, score);
}

add_score(scores, alice.view(), 30);
```

The outer borrow of `scores` lasts for the call's needs. It is **not** tied to
`keys`, which constrains the stored text. Both can be named if an API needs to
relate them, but ordinary calls infer the outer borrow.

A container remains generic over `K` and `V`. Its ordinary `insert(K, V)` API
carries any lifetime parameters inside those types. It needs no new public
`stores` or `stores_borrows` attribute. The implementation still needs verified
ownership of its typed storage; a raw pointer alone does not supply that fact.

The following stable helper must be rejected without an appropriate outlives
relationship, even when its body is visible:

```gti
void wrong<lifetime stored, lifetime incoming>(
    mut std::vector<std::string_view<stored>>& target,
    std::string_view<incoming> value) {
  target.push_back(value);  // incoming is not known to cover stored
}
```

This is repaired by using one lifetime where that matches the API, or an explicit
`requires outlives<incoming, stored>` constraint. A local inference convenience
cannot silently change the meaning of these explicit universal parameters.

### Returning borrowed data and rejecting escapes

```gti
std::string_view<a> text_of<lifetime a>(std::string&<a> owner) {
  return owner.view();
}

// Elision relates the sole input region to the result.
std::string_view text_of(std::string& owner) {
  return owner.view();
}

std::string_view<a> invalid<lifetime a>() {
  std::string local{"temporary"};
  return local.view();  // rejected: local cannot satisfy caller-selected a
}
```

The short `text_of` form may also be a public API: its declaration determines
the contract without examining its body. Returning a view of a by-value owning
parameter is still rejected; a generic type argument does not turn that local
parameter's storage into caller-owned storage.

## Semantic rules

### LT-1. Regions, parameters and origins

A lifetime parameter universally quantifies a region in a declaration. Each call
instantiates it with constraints on the actual argument and result regions.
Local omitted arguments instead introduce inference variables solved from the
body's control flow, uses and cleanup. The implementation must keep these two
roles distinct; a universally quantified input is not a hole to solve from the
callee's implementation.

Every checked borrow also keeps its actual origin place(s), access mode,
escape boundary, loan endpoint and transfer/drop behavior. Regions describe
validity relationships; they do not replace provenance or grant aliasing
permissions. Repeated use of one region name does not identify two owners as the
same place, authorize two overlapping mutable borrows, or make pointers safe.

A result declared with a region shared by several possible input origins retains
the permitted origins conservatively. More precise declared field/type
relationships can distinguish them. Public call checking uses the declaration's
contract, not a stronger assumption based on its current body.

### LT-2. Grammar and parameter kinds

The following fragments extend, rather than replace, GTI's existing grammar:

```text
lifetime_parameter = "lifetime" IDENTIFIER
lifetime_argument  = IDENTIFIER | "_" | "static" | "this"
reference_type     = existing_reference_type [ "<" lifetime_argument ">" ]
```

In `existing_reference_type`, `T&` is read-only and `mut T&` is mutable. The new
argument attaches to that reference, so `mut View<a>&<b>` separates the stored
view's region from the reference to its shell. `this` names the receiver borrow
inside a nonstatic method contract. Existing restricted `T&&` move declarations
retain their meaning and do not introduce another reference-shell region;
`T&&<a>` is rejected. Lifetime arguments carried inside the moved type remain
part of that type's checked contract.

Lifetime parameters are a third generic parameter kind alongside GTI's existing
type/value forms. They are permitted on functions, classes/structs, aliases and
concepts, with the same scoping discipline as existing generic binders. Kind
mismatches are errors. Lifetimes are neither expression values nor substitute
ordinary type arguments, and cannot be tested at runtime. Normalized contracts
that differ only in binder names or explicit versus elided spelling are the same
signature, not distinct overloads.

Named parameters scope over return types, parameter types, fields, requirements
and bodies. Shadowing a live lifetime binder is rejected; renaming a binder
without changing its relationships is semantically inert. Use `lifetime` as a
contextual declaration keyword to minimize identifier collisions.

A supplied generic argument list remains positional. Omitted trailing lifetime
arguments are filled according to context; omitted non-lifetime arguments keep
existing GTI rules. `_` can fill a lifetime position when a later argument must
be supplied. Recommend putting explicit lifetime parameters after type/value
parameters so `Borrowed<T>` stays concise. This does not require new named
generic-argument syntax or silently skipping an argument in the middle.

### LT-3. Local inference

Infer omitted lifetime arguments in local variable types, construction and
calls from initializers, subsequent stores, uses, reborrows, control-flow joins
and destruction. An empty local collection may acquire constraints from later
insertions. Inference is body-local plus checked declaration contracts; it does
not require inspecting external implementation bodies or guessing from a
particular execution path.

Use non-lexical endpoints where proven. Unknown/ambiguous ownership must produce
a diagnostic or a sound conservative result, never an unchecked pointer or an
implicit static lifetime. Explicit `_` requests contextual inference, not
permission to ignore an obligation. Unconstrained regions cannot escape into a
public signature, opaque callable or published module interface as unsolved holes.

### LT-4. Signature elision and public stability

Resolve declaration elision before checking its implementation:

1. Each omitted lifetime occurrence in input types introduces a fresh parameter.
   This includes omitted arguments of nested borrowed types; occurrences are not
   implicitly equated because their spelling is identical.
2. A method's elided output borrow defaults to its receiver borrow where that
   form is valid. This describes a borrow of the receiver's storage. An output
   intentionally tied to a stored external region should name that region when
   the receiver default is too restrictive.
3. Otherwise, if there is exactly one distinct input lifetime available, use it
   for elided output lifetimes. Ambiguous or input-free borrowed results require
   explicit relationships. An owning by-value input contributes no lifetime
   for a borrow of its own local shell.
4. Existing type arguments keep their lifetime relationships. Elision does not
   invent new independent lifetimes inside an opaque generic `T`.

Use `this` to name the receiver borrow explicitly: `T&<this>`, `View<this>`, or
`requires outlives<this, a>`. It is reserved for that context, not a generic
parameter that can be rebound. Stored external regions remain separately named.

Exported functions, concept operations, virtual methods, external declarations
and callable type signatures use a stable declared or mechanically elided
contract. In particular, a helper taking a mutable collection and an incoming
view generally needs a named relationship: independently elided input regions
cannot justify storage of one into the other.

Local lambdas and private, body-available helpers may infer a more general
relational summary when a signature is not a stable external boundary. The
compiler must record that inference, handle recursive groups with a finite fixed
point and show the inferred contract on request. An explicit signature is always
binding. The precise eligibility rule for private helpers and migration of
already-exported body-inferred APIs must be resolved before acceptance; no silent
public-contract inference is the default escape hatch.

The Rust elision rules are a useful precedent, not GTI authority. GTI's existing
field-sensitive contracts and proposed anonymous record parameters need their
own compatibility and soundness review.

### LT-5. Borrowed type declarations and anonymous parameters

For ordinary non-recursive records, each syntactically omitted stored reference
region or omitted borrowed-type argument introduces an anonymous region parameter
in a deterministic field-path order. Independent occurrences remain independent;
explicit names express equality or outlives requirements. A generic field of
existing type parameter `T` simply retains the regions carried by `T`.

This is declaration-based, so changing a constructor body cannot change the
public type's lifetime arity. Anonymous parameters must appear in normalized
compiler/tooling metadata even when source users omit them. An explicit form can
name the slots for advanced APIs. Recursive types, inherited fields and aliases
must have a finite canonical rule; if one cannot be determined, require explicit
parameters and diagnose the declaration. Do not infer arbitrary extra binders
by traversing an infinitely expanding type.

Adding/changing a borrowed field may change the type's declared contract just as
other public field changes can. Compatibility is assessed on that normalized
contract, not the absence of visible lifetime names in old source.

### LT-6. Bounds and static storage

Propose `outlives<a, b>` in a `requires` clause to mean region `a` covers all
points required by `b`. It is a core lifetime predicate, not a runtime call or
an application-defined boolean capable of asserting safety. A corresponding
`outlives<T, a>` checks that the borrowed components of type `T` meet the
required validity for `a`; it does not assert that a particular `T` object's
storage remains alive. Exact integration with GTI's existing requirements
language is an acceptance item.

```gti
int&<shorter> shorten<lifetime longer, lifetime shorter>(int&<longer> value)
    requires outlives<longer, shorter> {
  return value;
}
```

A well-formed `T&<a>` requires any borrowed components observed through `T` to be
valid for that access. Infer such well-formedness obligations where justified,
and serialize them with the signature. Do not turn them into arbitrary extra
requirements on unrelated type parameters.

`static` names validity supplied by genuinely static storage, such as immutable
literal characters. It does not promote a local, grant mutable global access,
extend a temporary, or waive thread/drop ordering rules. Static data may satisfy
a shorter region where the reference/type compatibility rules allow it.

### LT-7. Subtyping, reborrowing and variance

The initial proposed rules are structural:

- A read-only reference may shorten its region and covariantly preserve compatible
  borrowed referent types.
- A mutable reference may be reborrowed for a shorter region under existing
  exclusive-loan rules; the parent permission is suspended as required. Its
  referent type is invariant. A writable `Container<View<long>>` cannot be
  reinterpreted as writable `Container<View<short>>` and then receive a
  short-lived view.
- Owning aggregates can be covariant in parameters used only in covariant owned
  or shared positions. Conflicting uses, interior mutation through shared access
  and unproved opaque storage require invariance. Ordinary mutation requiring an
  exclusive receiver is not alone evidence of interior mutability.
- Callable arguments/results need the usual opposite/same-direction compatibility
  checks and their quantified lifetime contracts. Generic/invariant and mutable
  cases must have negative tests, not only a shared-reference demonstration.

Variance is inferred from verified type/storage structure, never granted because
a type is named `vector` or `string_view`. Raw-pointer-backed owners need a
validated ownership representation to claim the appropriate variance. Until
proven, invariance is the safe rule. Exact integration with GTI's raw pointer and
interior-mutation capabilities is an acceptance gate.

### LT-8. Storage and lifetime parameters inside generics

A value type's borrowed components retain their regions through `T`, aliases,
associated types, nested records and typed storage. References to the value's
shell are distinct from those stored components. Moving a carrier transfers its
borrow facts; a shared copy preserves them. No operation converts exclusive
permission into shared-copyable ownership merely because lifetimes are erased.

RFC 0003 adds per-point dependency updates for dynamic storage. Lifetime-bearing
types constrain which values can be stored; flow facts track which actual owners
are protected. Neither representation can contradict or replace the other.
Whole-value replacement can end old loans after cleanup, but cannot rebind an
explicit universal region or coerce an invariant referenced container to another
element contract. Local inference variables may be resolved across replacements
only when all surviving aliases and declaration constraints remain satisfied.

Low-level storage needs an ownership/drop description relating its live `T`
objects to the owner. Lifetimes alone do not establish which raw address belongs
to an owner, which slots are initialized, or which destructors run. This is a
general typed-storage mechanism, not a public per-operation `stores` attribute.
The unsafe contract and its phase representation must be settled with RFC 0003
before any borrowed raw-store admission. Existing `borrow_free` gates stay in
place until the complete read/write/cleanup path is proved.

### LT-9. Concepts, callbacks and opaque interfaces

Concept and virtual signatures use the same lifetime parameters, bounds and
elision rules. Implementations must satisfy the interface's quantification and
may not rely on a longer-lived argument than the interface promises. Matching a
native representation while changing the lifetime contract is not conformance.

A callable that works for *every fresh input lifetime* differs from one fixed to
a surrounding region. The model must represent both. Lifetime binders on named
function declarations already provide the former; first-class callable types
need equivalent higher-ranked quantification. The selected spelling places the
binder before the complete callable type:
`for<lifetime a> int&<a>(int&<a>)`. A closure's fixed environment regions are
separate from its per-invocation quantified regions. Concept/virtual conformance,
closure capture composition and erased-callable compatibility still require
their complete acceptance evidence.
Do not ship callable erasure by dropping the quantifier or inventing another
borrow attribute. Ordinary callback calls should infer lifetime instantiations.

### LT-10. Cleanup, failure and unsafe boundaries

Borrow validity includes all accesses made by destruction and partial-construction
rollback, not merely the final explicit source read. A view with passive cleanup
may have a shorter use lifetime than its container's storage lifetime, provided
verified cleanup never dereferences the expired external referent. Generic or
opaque destructors are conservatively treated as using relevant borrows unless a
checked contract proves otherwise. No blanket user `may_dangle` escape is added.

Keep existing destruction order, move rules, failure transport and evaluation
order. A failing operation must leave borrow facts consistent with any elements
it published and all cleanup it performs. Raw memory reads cannot manufacture an
ownerless value from a lifetime-bearing stored element. Unsafe construction and
native calls retain explicit validity, aliasing and ownership obligations; names
on reference types do not prove those obligations.

## Compiler and tooling design

| Layer | Responsibility and preserved facts |
| --- | --- |
| Lexer/parser/AST | Contextual `lifetime`, reference arguments, parameter-kind syntax, placeholders, bounds and exact spans; no borrow-policy decisions |
| Semantic analysis | Region binders/variables, elision, type well-formedness, variance, bounds, actual origins, access/escape rules and checked declaration summaries |
| HIR | Preserve concrete type identities plus region substitutions and verified borrow/storage contracts; lifetimes must not be rediscovered from layout |
| MIR | Body-local flow/liveness, transfers, joins, cleanup paths and independent checking of semantic borrow obligations; no repair of missing language rules |
| LLVM | Consume proved operations and erase region-only metadata from execution; do not duplicate implementations solely for lifetime substitutions |
| Driver/module metadata | Serialize normalized binders, bounds, variance, relevant origin/storage/drop contracts and schema/version identity for future independent callers |
| Formatter/Tree-sitter/LSP | Parse/format all forms, distinguish lifetime identifiers, offer hover/rename/completion, show inferred contracts and connect errors to invalidating owners |

Use one canonical region/binder identity system across reference carriers and
owner-dependent text. Audit and subsume existing single-owner and nominal shape
exceptions rather than adding another semantic path for each library wrapper.
Existing `borrowed_from` must translate into this model rather than retain a
parallel lifetime solver.

Declaration summaries are semantic authority. Body-local fixed points can be
computed or independently checked with MIR infrastructure, but phase timing must
remain explicit: signature/generic checking cannot require completed whole-
program MIR. Preserve staged queries and invalidation identities for incomplete
LSP source. A cached result must be invalidated by a changed region contract,
field declaration, destructor contract or capability proof, even when runtime
layout is unchanged.

Diagnostics should name owners and operations first: which value was stored or
returned, which owner would end, and which declaration requires a longer borrow.
For ambiguous elision, show explicit candidate signatures without guessing the
user's intended relationship. A fix-it is offered only when mechanically safe.
Adding `static` is not an automatic repair. Related locations should include the
region binder, retaining operation and invalidating scope/move/mutation.

Only type/value substitutions that change executable behavior should multiply
native code instances. Preserve semantic distinctions until verification, then
use a lifetime-erased codegen key where sound. Alpha-renaming must not create
new type-layout variants, runtime descriptors or duplicate native code. Semantic
metadata remains versioned; erasure is not a cross-version ABI guarantee.

## Compatibility and migration

This deliberately revises the current "no source lifetime parameters" direction.
It does not erase the earlier rationale or claim the new model already exists.
Implementation updates the canonical ownership, grammar, concepts, type/trait,
HIR/MIR, tooling and compiled-interface documents alongside runnable examples.

Keep ordinary `T&`, `mut T&`, bare `std::string_view` and simple borrowed-record
uses through deterministic elision/inference where their old behavior is sound.
Anonymous region parameters are intended to preserve existing aggregate
construction ergonomics. A source compatibility inventory must identify all
cases that instead need explicit parameters, including exported body-inferred
returns and generic overload/alias interactions. Do not promise zero breaking
changes before that inventory passes.

Retain `[[borrowed_from(owner)]]` and `[[borrowed_from(this)]]` initially as checked
shorthand lowered into the same core relationships. Explicit lifetime parameters
and an attribute must agree when both occur; contradiction is diagnosed. Which
advanced origin-projection information must remain alongside lifetime types is a
review item: validity parameters cannot replace all origin/place facts. Do not
add `stores` or `stores_borrows` as an alternate public lifetime mechanism.

No existing object-layout/ownership meaning changes merely by adding an omitted
region argument to a borrowed type. Overload matching, canonical semantic type
identity, aliases and reflection need defined lifetime-aware behavior; ordinary
reflection must not turn erased regions into runtime values. A layout or
erased-type equality query cannot authorize a reference conversion that violates
lifetime or access rules. Versioned interface
metadata must distinguish a changed borrow contract even if object code is
identical. Installed toolchains must reject incompatible metadata clearly.

No compiler branch, VERSION, changelog or release artifact changes belong to this
proposal PR. Later implementation follows GTI's ordinary changelog and integration
policy, with a migration note for any accepted incompatibility.

## Safety and correctness

Required invariants:

1. Every use, escape and borrow-observing cleanup is covered by a valid region
   and by compatible actual origin/access facts.
2. Callees satisfy universal declared contracts for every permitted
   instantiation; they cannot select convenient caller lifetimes internally.
3. Mutable aliases cannot change a referent's lifetime-bearing element type
   through covariance. Reborrows do not duplicate exclusive permission.
4. Public/opaque callers need only the declared normalized contract. Body edits
   cannot silently strengthen it or make callers depend on implementation-only
   precision.
5. Construction, moves, copies, replacement and failure cleanup preserve the
   complete dependencies carried by a generic value.
6. Raw/erased storage and callable interfaces cannot launder lifetime information.
   Unsafe boundaries explicitly account for live objects, drop behavior and
   provenance; lifetime annotations are not proofs of raw memory validity.
7. Constraint solving and recursive inference terminate or produce a bounded,
   actionable resource diagnostic. Exhausting a budget never admits unsafe code.

Review the rule inventory and counterexamples with
[RFC 0002](0002-borrow-checker-verification.md). That verification campaign is a
related source of evidence, not a circular prerequisite or a substitute for
reviewing the formal contract. Examples and successful tests alone are not a
proof of soundness.

## Performance and resource costs

No performance measurements exist for this proposal. Required cost model:

- Region names/constraints add no runtime fields, counters, dynamic checks,
  allocations, pointer indirections or per-call lifetime arguments.
- Equal executable types/bodies should retain their existing layout and cost.
  Lifetime-erased instantiation must avoid native code growth from region names.
- Borrowed container workloads may avoid owned copies, but that is a result to
  measure under RFC 0003, not an automatic speedup claimed by this RFC.
- Compile-time and compiler-memory costs include constraint solving, variance,
  binder canonicalization, metadata and body-inferred summary fixed points.
  Use indexed/shared facts, body-local scopes and invalidation instead of
  unrestricted whole-program inference.
- LSP costs include incremental reparsing and changed-contract propagation.
  Repeated edits in large generic code must be measured and bounded.

Compare explicit and elided versions of identical workloads: returned references,
borrowed records, nested generic wrappers, iterator pipelines and callbacks;
with RFC 0003 add tokenization, word count and indexes of views. Record runtime,
allocation count, native code size, compilation time, peak memory and LSP edit
latency. Runtime material regressions fail acceptance unless the owner explicitly
accepts the documented tradeoff. No safety rule may be dropped to recover speed.

## Alternatives and tradeoffs

- **Growing relationship attributes:** small initial edits, but each new storage,
  result or interface boundary risks a separate contract language. A sufficiently
  general attribute notation is itself a lifetime system; avoiding angle-bracket
  parameters is not a reason to prefer it. Keep useful existing shorthand only
  when it maps to the common semantics.
- **Hidden lifetimes everywhere:** attractive locally, but difficult to name in
  diagnostics or stable multi-input APIs. This proposal keeps inference and adds
  explicit names where needed.
- **Always explicit parameters:** predictable but burdens ordinary usage and
  existing simple borrowed records. Elision is a required part of this design.
- **Rust-style apostrophes:** a proven recognizable spelling, but the owner
  prefers `lifetime a`, `T&<a>` and GTI's existing generic placement. Adopt useful
  semantic lessons without making Rust's syntax or behavior GTI's authority.
- **Construction-fixed/scoped-only borrowing:** simpler implementation but does
  not cover the requested reusable containers and APIs. It remains a bounded
  current capability, not the long-term target.
- **Runtime handles or shared ownership:** useful explicit abstractions with
  different ownership/cost models; they do not replace static borrowed views.

The proposed form increases the explicit type-system surface. Its justification
is one compositional relationship model across independent libraries, paired
with a predictable omission policy. It must not grow into ad hoc per-library
exceptions under a new spelling.

## Unresolved questions

The selected notation and inference-first goal are drafting direction. Before
acceptance, resolve these semantic/compatibility gates explicitly:

1. Final grammar and normalization for anonymous regions through aliases,
   inheritance and recursive records; explicit naming of an existing anonymous
   field slot without an accidental contract change.
2. Exact eligibility for private body-inferred helpers and migration of current
   exported body-inferred contracts. Stable interfaces must remain inspectable
   without bodies.
3. Receiver-region composition and move compatibility evidence. The selected
   spelling is `this`; existing restricted `T&&` declarations do not receive
   a reference-shell lifetime annotation.
4. Concept/virtual conformance, closure environment versus invocation binders,
   and erased-callback compatibility. The callable binder spelling is
   `for<lifetime a> R(Args...)`; do not discard obligations at erasure.
5. `outlives` integration with requirements, well-formedness implied bounds,
   overload resolution and lifetime-aware reflection/type identity.
6. Variance and drop-use contracts for raw-storage/interior-mutation owners.
   RFC 0003 storage admission is blocked until the relevant invariant is proved.
7. Contract metadata versioning and compatibility with the existing compiled-
   artifact foundation; lifetime erasure must not hide semantic API changes.
8. Quantitative compile-time/memory/LSP budgets after establishing baselines.
   Ergonomics results must list where annotations are required and why.

These are concrete proof/design obligations, not authorization to silently choose
an unsafe default. Smaller implementation slices may proceed only after their
own design is accepted and must preserve the stated extension boundaries.

## Implementation plan

No slice is implemented or authorized by this draft. Track later execution in
GTI with links back here; do not duplicate an implementation roadmap here as a
claim of completion.

| Slice | Coherent outcome and prerequisites |
| --- | --- |
| L0 | Resolve acceptance questions, normalized contract model and compatibility/ergonomics corpus; document the amendment to the no-parameters direction |
| L1 | Parser/AST/formatter/Tree-sitter/LSP support plus semantic binder/kind identities; reject unsupported uses explicitly, with no new unchecked execution |
| L2 | Checked explicit reference/record functions, bounds, reborrowing, variance and cleanup through HIR/MIR/LLVM; positive and negative ordinary user-type cases |
| L3 | Local inference, signature elision, anonymous-record rules and private-summary policy; preserve the annotation-free corpus and stable public declarations |
| L4 | Generic nested regions, concepts, quantified callables, normalized interface metadata and one core translation for existing borrow attributes |
| L5 | Joint boundary with RFC 0003: verified typed-storage lifetime/drop contracts before its M3/M4 admission; no intermediate public stores attribute |

L2-L4 require the corresponding L0 decisions; syntax support alone is not a
usable feature. L5 is a dependency handoff, not a requirement that RFC 0003 land
before this RFC's basic reference/record functionality. Deliver vertical slices
with their tooling, examples, documentation and verification, not a long-lived
parser feature falsely reported as lifetime support.

## Validation and release criteria

Document-only checks for this proposal: regenerate the RFC index, run the RFC
checker and `git diff --check`. Compiler validation is required for future
implementation, not for this draft PR.

Required implementation evidence:

- **Syntax/tooling:** all proposed forms, mixed generic kinds, nested closing
  brackets, binder shadowing, unknown names, `_`, `static`, incomplete edits,
  formatter idempotence, token kinds, hover, rename and safe diagnostic spans.
- **Inference/elision:** explicit/elided equivalence; identity and sole-input
  views; receiver defaults; multi-input rejection; separate stored and receiver
  regions; local empty containers and later insertions with RFC 0003; private
  recursive summaries and changed public bodies retaining their declared APIs.
- **General types:** unrelated borrowed records, multiple independent regions,
  nested generic wrappers, aliases, associated types, omitted trailing lifetime
  arguments, explicit holes and illegal kind substitutions. Preserve the
  existing multi-service borrowed-aggregate example where sound.
- **Safety negatives:** local/temporary escape, by-value-owner shell escape,
  unrelated universal-region insertion, short-lifetime insertion through a
  mutable long-lifetime container, duplicate mutable aliases, reborrow misuse,
  invalid static claims, raw-read laundering and unsound callable erasure.
- **Lifecycle execution:** moves/copies, destructor reads, passive cleanup,
  partial construction failure, replacement, nested carriers and callbacks;
  copied external views versus references into carrier storage must differ.
- **Boundaries:** declaration-only and serialized-contract consumers produce
  the same accept/reject results as available-body checking; interface
  conformance and changed-contract invalidation are verified independently.
- **Ergonomics:** runnable programs for local borrowed use, a multi-input API,
  independent parser/context borrows and a user-defined generic abstraction.
  With RFC 0003, add map/vector examples. Record remaining annotations rather
  than claiming all library authors or all application code can omit them.
- **Performance:** the representative workloads and costs above, with explicit
  and inferred versions sharing equivalent executable work.

Use an optimized host compiler and LLVM runtime modes at O0/O3 under GTI's
current focused-validation policy, plus affected compiler/tooling tests, pipeline
and native smoke. The merge queue and post-integration jobs prove integration;
do not run a full local compiler suite merely to publish the feature. C++ backend
parity is not a gate. Add runnable `examples/`, canonical specification updates
and changelog fragments with implementation. Release availability remains
separate from draft, accepted and implemented status.

## Decision record

- **2026-11-06, owner drafting direction:** the owner preferred a uniform lifetime
  system over proliferating relationship attributes, selected the illustrated
  `lifetime a` / `T&<a>` form, and requested this RFC with inference/elision keeping
  annotations out of most code. The owner also requested RFC 0003 depend on it.
- **2026-11-06, implementation authorization:** the owner subsequently requested
  end-to-end implementation by the primary agent and two subagents. Work is
  recorded in [implementation PR 302](https://github.com/lang-gti-official/gti/pull/302).
  This is authorization to implement, not evidence of completed validation.
- **2026-11-06, implementation refinements:** use the reserved receiver region
  `this`, the callable binder `for<lifetime a> R(Args...)`, and no explicit
  lifetime on the existing restricted `T&&` move spelling. Keep fixed closure
  environment regions distinct from per-invocation regions. Anonymous field
  slots remain declaration-derived; checked initializer-list provenance may
  infer constructor relationships into those slots without changing their arity
  or silently weakening explicitly named owner-region contracts.
- **Pending:** complete semantic/compatibility evidence and a durable formal
  acceptance record. The proposal remains a draft until its Decision field is
  updated through the repository's decision process; it is not marked implemented.

## References

- [RFC 0003](0003-borrowed-container-elements.md): consumer of the lifetime model;
  dynamic shared-borrow storage, dependencies and container cleanup.
- [RFC 0002](0002-borrow-checker-verification.md): independent verification and
  adversarial cases for new borrow rules.
- [GTI ownership](https://github.com/lang-gti-official/gti/blob/adbe89e5644414939707f8de4069fa2aca7a0baf/docs/language/ownership-and-lifetimes.md),
  [raw pointers](https://github.com/lang-gti-official/gti/blob/adbe89e5644414939707f8de4069fa2aca7a0baf/docs/language/raw-pointers.md),
  [grammar](https://github.com/lang-gti-official/gti/blob/adbe89e5644414939707f8de4069fa2aca7a0baf/docs/language/grammar.ebnf),
  [concepts](https://github.com/lang-gti-official/gti/blob/adbe89e5644414939707f8de4069fa2aca7a0baf/docs/language/concepts.md):
  current semantics, syntax and boundaries this proposal extends.
- [GTI architecture](https://github.com/lang-gti-official/gti/blob/adbe89e5644414939707f8de4069fa2aca7a0baf/docs/architecture/overview.md),
  [HIR](https://github.com/lang-gti-official/gti/blob/adbe89e5644414939707f8de4069fa2aca7a0baf/docs/architecture/hir.md),
  [MIR](https://github.com/lang-gti-official/gti/blob/adbe89e5644414939707f8de4069fa2aca7a0baf/docs/architecture/mir.md):
  phase authority and checked facts to preserve.
- [ADR 018](https://github.com/lang-gti-official/gti/blob/adbe89e5644414939707f8de4069fa2aca7a0baf/docs/decisions/018-loan-erasure-representation.md):
  loan erasure and the existing runtime-cost commitment; historical C++ details
  do not change today's LLVM-first backend policy.
- [Rust lifetime elision](https://doc.rust-lang.org/reference/lifetime-elision.html):
  precedent for deterministic signature omission, not GTI's full elision policy.
- [Rust subtyping and variance](https://doc.rust-lang.org/reference/subtyping.html):
  precedent for mutable referent invariance and quantified lifetime compatibility.
- [Rust drop checking](https://doc.rust-lang.org/nomicon/dropck.html):
  precedent for treating destructor observations as validity obligations.
