# RFC 0003: Borrowed elements in containers

| Field | Value |
| --- | --- |
| Status | draft |
| Authors | @gti-language-official (with Claude) |
| Created | 2026-11-06 |
| Updated | 2026-11-06 |
| Area | language |
| Proposal | https://github.com/lang-gti-official/rfcs/pull/3 |
| Decision | pending |
| Implementation | none |
| Supersedes | none |
| Superseded by | none |

## Summary

Let checked borrows live inside containers, so that
`std::vector<std::string_view>` over local strings and
`std::unordered_map<std::string_view, int>` compile and stay memory safe, with
no runtime cost and no change to how a view is represented.

The central storage change is that a value's dependency set may **grow after
construction**. Storing a borrowed value into an existing owner adds its actual
owner dependencies, which remain protected for the required uses and cleanup.
Lifetime-bearing types constrain which stores are permitted; checked body-flow
facts track the actual owners involved. A trusted typed-storage boundary still
has to establish what source-defined storage owns.

**Prerequisite: [RFC 0004, lifetime parameters with inference and
elision](0004-lifetime-parameters-and-elision.md).** This draft now uses its
`lifetime a`, `T&<a>` and borrowed-type arguments, with inference and elision for
ordinary usage. It does not propose a new `stores` attribute. RFC 0004 must be
accepted, and its relevant type, contract and storage obligations established,
before this RFC's boundary/storage admission stages. Independent preparatory
work remains subject to its own authorization and validation; see
[the prerequisite decision](#prerequisite-decision-lifetime-syntax).

This is a draft. Nothing here is implemented, and it changes no language
permission today.

## Motivation and goals

GTI programs that process text must currently own every piece they keep. A
tokenizer, an index over a loaded file, or a word count either clones each
string or stores offsets by hand. The cost shows up directly at the call site:
`std::unordered_map<std::string, int>::operator[]` takes an owned key, and
`std::string` has a deleted copy constructor, so a named key must be written
`counts[word.clone()]`, which allocates even when the key is already present.
With a view key, `counts[word]` would need no allocation, because
`std::string_view` is copyable.

Goals:

1. Admit shared borrows as container elements and keys for general,
   source-defined containers, not just for `std::vector`.
2. Keep the guarantee that a retained borrow can never outlive or observe a
   mutation of its owner, with rejection at compile time.
3. Add no runtime state. Loans continue to erase
   ([ADR 018](https://github.com/lang-gti-official/gti/blob/4c71f55c9c560ae6830829cd9ca466087d9bbe8c/docs/decisions/018-loan-erasure-representation.md)).
4. State every rule without naming a `std::*` type, and prove it with an
   unrelated user-defined container.

Success means the programs in the guide-level section compile and run, the
listed unsound variants are rejected, and an unrelated user container gets the
same behavior through the same rules.

### Current evidence and limits

Observed on nightly 0.493.3 (`df1692ea`) on 2026-11-06, using small compile
probes:

| Program shape | Today |
| --- | --- |
| Class with two `int&` fields from two owners | Builds and runs |
| Write to one of those owners while the carrier is live | Rejected, `GTI-S2017` |
| `std::optional<std::string_view>` over a local string | Builds and runs |
| Generic `Box<std::string_view>` over a local string | Builds and runs |
| Carrier nested in a carrier field | Builds and runs |
| Literal stored through a `string_view` parameter into a global | Builds and runs |
| Two text fields from two different owners | Rejected, `GTI-S2045`: "would add a second owner dependency" |
| `v = t.view()` on an existing view | Rejected, `GTI-S2045` |
| `Holder[2]` of reference carriers, `std::string_view[1]` of a dynamic view | Rejected, `GTI-S2045` |
| `std::vector<Holder>` | Rejected, `GTI-S2029`: `vector_element` |
| `std::vector<std::string_view>` with `push_back(s.view())` | Rejected, `GTI-S2045`: raw storage |
| `std::vector<std::string_view>` with `push_back("literal")` | Rejected, same diagnostic |
| `std::unordered_map<std::string_view, int>` | Rejected, no `std::hashing` conformance; with a custom hash, rejected by `GTI-S2045` |

The foundations this proposal builds on are real but bounded: conflict-checked
multi-owner carriers, field-wise origin maps, inferred text field contracts with
recursive fixed points, cleanup-aware dependency retention, and
`[[borrowed_from]]` result contracts. The plan rows
`R-READ-BORROW-CARRIERS`, `R-MUTABLE-STORED-BORROWS` and `R-DYNAMIC-VIEWS` record
these as bounded, with reseating and storage transforms as gaps.

Four obstacles remain, in decreasing order of depth:

1. **Dependencies are fixed at construction.** The ownership specification keeps
   "assignment that would replace a carrier's dependency" rejected. A container
   gains owners after it exists, so this is the central change.
2. **No contract says an argument flows into a receiver.** `[[borrowed_from]]`
   relates a result to an input. `push_back` needs the reverse direction.
3. **Source-defined storage is opaque.** `std::storage_element<T>` requires
   `std::meta::is_borrow_free<T>()`, and raw construction refuses checked
   borrowed state "without a tracked destination owner". All `std::vector`
   element construction reaches one helper,
   [`construct_value_at`](https://github.com/lang-gti-official/gti/blob/4c71f55c9c560ae6830829cd9ca466087d9bbe8c/stdlib/std/detail/memory_storage.gti#L11),
   which is where the text diagnostic fires.
4. **Text and reference carriers follow different models.** A class may hold
   `int&` from several owners, but text is limited to one owner per value.

## Non-goals

- **Exclusive elements.** `std::vector<mut T&>`-style elements and mutable views
  are deferred. Shared borrows are the first scope (BC-13).
- **Global, static, captured and cross-thread storage.** A value with a
  non-empty dependency set still cannot reach these destinations.
- **Self-referential values.** A value cannot depend on its own root (BC-6).
- **Per-element precision.** Dependencies belong to the whole root binding.
  Removing an element does not release its owner.
- **Defining a second lifetime surface.** Syntax, variance, elision, bounds and
  stable declaration contracts belong to prerequisite RFC 0004. This RFC must
  compose with that model rather than introduce per-operation borrow attributes.
- **Heterogeneous lookup.** A `Borrow`-style query that finds a `std::string` key
  from a `string_view` is a separate library proposal, though it is useful
  beside this work.
- **New allocation or container redesign.** `R-ASSOCIATIVE-CONTAINERS`
  follow-ups stay separate.

## Guide-level design

All examples in this section require this proposal unless marked otherwise.
Explicit lifetime forms and omitted lifetime arguments also require RFC 0004.
Hashing support and other container prerequisites remain part of this RFC's
implementation plan; these snippets are not claims that today's toolchain accepts
them.

A container of views keeps every viewed owner borrowed:

```gti
std::vector<std::string> lines = read_lines();
mut std::vector<std::string_view> kept{};
for (auto& line : lines) {
  if (line.size() > std::size_t(0)) {
    kept.push_back(line.view());   // kept now depends on lines
  }
}
print_all(kept);
```

The word count from the motivation stops allocating per lookup:

```gti
mut std::unordered_map<std::string_view, int> counts{};
for (auto& word : words) {
  counts[word.view()]++;   // a copyable view is the owned key
}
```

The failure cases are the point of the feature:

```gti
mut std::string line = read_line();
mut std::vector<std::string_view> parts{};
parts.push_back(line.view());
line.clear();         // GTI-S2017: parts depends on line
parts.size();         // ... because parts is used here
```

```gti
mut std::vector<std::string_view> parts{};
{
  std::string local = read_line();
  parts.push_back(local.view());
}                     // error: local ends while parts still depends on it
parts.size();
```

Dependencies end at the last use, and whole-value replacement drops them:

```gti
mut std::string line = read_line();
mut std::vector<std::string_view> parts{};
parts.push_back(line.view());
parts.clear();        // does not release line: the set never shrinks here
parts = std::vector<std::string_view>();  // this does release it
line.clear();         // valid
parts.size();
```

A stable helper states the relationship once; callers infer its arguments:

```gti
void remember<lifetime a>(
    mut std::vector<std::string_view<a>>& out,
    std::string_view<a> word) {
  out.push_back(word);
}
```

The mutable borrow of `out` is separately elided for the call. It does not last
for the stored views' region `a`. Private helpers and local lambdas may use
body inference under RFC 0004's eligibility rules; exported/opaque signatures
must not silently infer a stronger relationship from their implementation.

A concept operation uses the same lifetime arguments and checked conformance:

```gti
concept view_sink<S, lifetime a> {
  void add(mut S& sink, std::string_view<a> word);
};
```

This constrains the inputs an implementation must accept; it does not assert
that every implementation actually stores the word. A concrete receiver's
lifetime-bearing element types determine whether retaining it is legal.

A generic owner accepts its declared element type `T`. A trusted low-level
append operation can therefore retain an ordinary `T` without an extra `stores`
annotation, but its raw storage still needs a verified live-element ownership
and drop contract. The signature alone cannot prove which raw address belongs
to the receiver. BC-11 and RFC 0004 LT-8 gate that boundary.

## Semantic rules

### Terms

- A **carrier** is a value holding at least one checked borrow.
- The **dependency set** `D(b)` of a binding at a program point is the set of
  owners, paths and access modes the value in `b` retains.
- The **root** of a place is the binding that owns its storage.
- A **retaining store** writes a value into storage reachable from an existing
  root: an element, a field, a referent through `mut T&`, or a callee's flow
  summary.

### Dependency flow

**BC-1. Dependency sets are per-point facts.** `D(b)` tracks actual origins and
access at a program point. Lifetime parameters separately occur in types under
RFC 0004. These representations must agree: a type constrains permitted validity
relationships, while `D(b)` conservatively covers actual retained owners. Neither
is runtime state, and a lifetime name does not identify an owner.

**BC-2. A retaining store widens.** Storing `x` into a place under root `b` sets
`D(b) := D(b) ∪ D(x)`. This includes a store through a mutable reference whose
exact origin is known, and an element write through a mutable subscript. A
reference that may select among several roots widens every candidate.

**BC-3. Whole-value replacement narrows.** Assigning to an exact local binding
with no live reborrow sets `D(b) := D(x)`, after the old value's cleanup. A store
through a reference is always a widening. Operations such as `clear`, `erase` or
`pop_back` do not narrow. This flow update does not rebind an explicit universal
lifetime or change an invariant borrowed container's declared element type;
replacement must also satisfy RFC 0004's type and alias constraints.

**BC-4. Joins union, and loops reach a least fixed point.** Owners come from the
finite places of the enclosing body plus symbolic formal entries, so the
computation terminates. An element-derived owner is the whole parent owner: a
view of `strings[i]` depends on `strings`.

**BC-5. Protection and endpoints.** Each owner in `D(b)` stays protected for its
access mode until the last use of `b`, or until cleanup finishes where BC-8
requires it. A borrow taken from a range element and stored this way outlives
the iteration's child loan, so the parent range owner remains read-borrowed after
the loop.

**BC-6. No self-dependency.** A store whose `D(x)` contains the destination's own
root is rejected, because the root could never again be moved or mutated.

**BC-7. Reading from a carrier.** Copying a value out of `b` yields a value with
`D(b)` and no loan on `b`, so `v.push_back(v[0])` is valid once the operand is
copied. A reference to an element holds a loan on `b` and separately retains
`D(b)`, matching the existing distinction between a carrier's physical storage
and its stored dependency.

**BC-8. Cleanup.** An owner's cleanup uses a dependency only if concrete element
cleanup does. A `std::vector<std::string_view>` releases memory without reading
its elements, so it may be declared before the string it views. A container of
elements whose destructors read the dependency retains it until cleanup finishes,
so the same declaration order is rejected.

### Function boundaries

**BC-9. Flow summaries.** Body-local summaries track source-to-target stores and
actual origin dependencies, including recursive fixed points. A local's
borrow escaping into caller-owned storage is rejected. These facts must obey
RFC 0004's lifetime-bearing types and declaration constraints; they cannot equate
unrelated explicit input lifetimes merely because a body attempts a store.
At opaque/public calls, use the declared contract and conservatively preserve
all permitted dependencies rather than relying on private body precision.

**BC-10. Declared contracts.** Functions, concepts, virtual operations and erased
callables use RFC 0004's parameter/bound/elision model. Stored and incoming
regions are related through the element types and signature, as in `remember`
above. Multi-origin results use shared or distinct named regions according to
the intended relationship. Implementations must satisfy their declared
quantification. There is no new `stores` attribute or competing public summary
language. Existing `borrowed_from` compatibility follows RFC 0004.

### Storage and unsafe code

**BC-11. Tracked storage.** A raw store of a dependency-carrying value remains
rejected without a validated typed owner and matching lifetime-bearing element
contract. The unsafe implementation must establish which live objects belong
to that owner, their origin/access dependencies and their cleanup behavior.
Safe wrappers compose those facts through ordinary generic types. A raw pointer
alone cannot be the tracked owner because its address does not supply those
ownership facts. RFC 0004 LT-8 defines the common model; the exact low-level
storage interface is an unresolved admission gate, not replaced by a `stores`
attribute or discharged merely by naming a lifetime.

**BC-12. Reads from tracked storage are never ownerless.** A dependency-capable
result preserves the dependencies required by its declared lifetime-bearing
type and verified storage/origin contract. Without a proven narrower mapping,
retain all possible external dependencies; never infer ownerless merely because
the physical load uses a raw pointer. This matters because
[`rawMemoryText`](https://github.com/lang-gti-official/gti/blob/4c71f55c9c560ae6830829cd9ca466087d9bbe8c/src/compiler/mir_text_contracts.cpp#L28)
currently treats text read from raw memory as inert. That is sound only while no
dependent text can be stored there. Under this proposal an unchanged rule would
let `v.pop_back()` return an apparently ownerless view of a dead string, so this
rule must land in the same slice as admission.

**BC-13. Element admission.** A tracked owner admits elements with shared
dependencies only. An element type holding an exclusive dependency stays rejected
for now. `std::meta::is_borrow_free<T>()` keeps its meaning, and clients that
need it, such as thread transfer and polymorphic models, keep requiring it.
`std::storage_element<T>` relaxes to a new structural query.

### Interaction with existing features

**BC-14. Moves, copies and swaps.** A move transfers `D` and ends the source.
`clone` and shared copies retain `D`. Swapping two carriers is a pair of flow
edges in the summary, and an exact local swap may treat both as replacements.

**BC-15. Failure paths.** A call with a store edge widens on every outgoing edge,
including failure. This over-approximates and is sound. Failure cleanup observes
the widened set.

**BC-16. Boundaries that stay closed.** Globals, statics, escaping captures,
thread transfer and native calls reject a non-empty `D`. Targets reached through
a stored reference, such as a `Sink` class holding `mut std::vector<...>&`, are
rejected in the first version, because the widening would have to reach an owner
the caller cannot see from the call expression.

## Compiler and tooling design

| Layer | Work |
| --- | --- |
| Parser, AST, grammar | Reuse RFC 0004 lifetime syntax and elision; no container-specific contract attributes |
| Semantic analysis | Rule authority: retaining stores, summaries, contract validity, element admission, new diagnostics |
| HIR | Preserve store events, summaries and proof records per concrete instance |
| MIR | Dependency sets over the CFG in the ownership fixed point, plus an independent re-derivation in verification |
| LLVM backend | No representation change expected, since loans erase; coverage entries for newly admitted shapes |
| Standard library | Storage contracts, `storage_element`, `std::hashing` and ordering for `string_view` |
| LSP, formatter, Tree-sitter | New syntax; diagnostics with related locations; editor cost budget |

The nearest precedent is the ownerless text contract. A proof is recorded by the
semantic model, carried by `hir_lowering`, and re-derived by
`verifyOwnerlessTextContracts` in the MIR verifier. This proposal follows that
shape: semantics owns the rule, and MIR verification must not invent it. The
[architecture table](https://github.com/lang-gti-official/gti/blob/4c71f55c9c560ae6830829cd9ca466087d9bbe8c/docs/architecture/overview.md)
gives MIR "ownership/lifecycle fixed-point verification" and denies it "language
rules missing from semantics/HIR". Because dependency sets are control-flow
facts, the exact split is an open question.

The implementation cost is large. `containsBorrowedState` has 584 references in
`src/` at this revision, and many current rules are admissions of specific
shapes. A general set representation has to replace those decisions rather than
add another one. The single-owner text model is the largest such replacement.

Diagnostics need a chain of explanation. A conflict on `line` must point at the
store that added the dependency, for example "`parts` depends on `line` because
of this `push_back`", and through summaries where a helper performed the store.
New codes follow the add-diagnostic process; none is assigned here.

C++ backend parity is not an acceptance gate.

## Compatibility and migration

Container admission is intended to extend currently rejected shapes. The
combined feature's source compatibility also depends on RFC 0004's lifetime
migration and elision inventory; this RFC does not promise that every existing
body-inferred public API remains unchanged. Rejections that move or change
wording need test updates.

This proposal revises several recorded boundaries, which stay in place until a
decision changes them:

- `ownership-and-lifetimes.md`: "arrays of borrowed carriers ... and assignment
  that would replace a carrier's dependency remain rejected".
- `implementation-sequence.md`: dynamic text views reject "reassignment/reseating
  and storage in globals, fields, fixed arrays, or dynamic storage", and
  associative containers do "not admit borrowed-state container elements".
- `place-and-ownership-state.md` section 10 on dependency-reseating assignment.
- The concepts specification's single-origin requirement result.

RFC 0004 proposes the explicit revision of "No source lifetime parameters are
introduced" in `ownership-and-lifetimes.md`. That change is owned by its
acceptance and migration work, not silently made by container admission.

Stable public/opaque contracts are determined by lifetime-bearing declarations
and mechanical elision. Private body inference may still participate under RFC
0004's rules. Preserve that distinction when migrating existing inferred text
contracts and serializing compiler summaries.

## Safety and correctness

Invariants:

1. **Containment.** At every point, every borrow reachable from a root is covered
   by that root's dependency set.
2. **Protection.** No owner in a live root's set is mutated, moved or destroyed.
3. **Monotonic widening.** Only BC-3 narrows a set, and only for an exact local.
4. **Declared covers derived.** A contract is a superset of what a safe body does.
5. **No ownerless laundering.** A dependency-capable value leaving tracked storage
   cannot appear ownerless.

Specific risks reviewers should examine:

- **Laundering through raw reads** (BC-12): the most concrete known hazard.
- **Aliased stores:** a store through a mutable reference must reach the true
  root. A missed widening is a use-after-free with no diagnostic.
- **Unsafe storage:** a false live-element ownership/drop contract breaks
  containment even when lifetime types look correct. Keep the trusted boundary
  small and audited, and verify reads as well as construction/destruction.
- **Order of evaluation:** `v.push_back(v[0])` must finish the read before the
  exclusive receiver activates.
- **Relocation:** growth moves elements inside the owner. Sets are per root, so
  this needs no update, but carriers with reference fields need relocation
  evidence.

Tests cannot prove these. Because a missed widening fails silently, this work
should feed [RFC 0002](https://github.com/lang-gti-official/rfcs/pull/2)'s rule
inventory and independent model, and its adversarial generation should cover
stores through aliases, loops and summaries. RFC 0002 is itself a draft, so this
is a recommendation rather than a dependency.

## Performance and resource costs

No measurements exist yet. These are expectations to check.

- **Runtime:** none added by the rules, since loans erase. Programs that move from
  owned strings to views should allocate less, and that needs a benchmark.
- **Code size:** new instantiations such as `std::vector<std::string_view>`.
- **Compile time:** per-point sets over a body's owners, plus cross-function
  fixed points. Set size is bounded by owners in scope, but large generated
  bodies need measurement.
- **Editor:** inferred summaries widen what a body edit invalidates. Per-edit
  latency is an acceptance criterion, not an assumption.

Representative workloads: a tokenizer, a word count on `unordered_map`, and a
file index. Compare an owned baseline, a view version, and Rust's `HashMap<&str, _>`
for reference.

## Alternatives and tradeoffs

### Prerequisite decision: lifetime syntax

**Drafting direction chosen on 2026-11-06:** this RFC depends on
[RFC 0004](0004-lifetime-parameters-and-elision.md). The owner selected its
`lifetime a` / `T&<a>` form with inference and elision keeping annotations out
of ordinary use. Both documents remain drafts; this records the requested
proposal direction, not acceptance of their complete semantics or permission
to implement them.

The reason is the repeated need to relate arguments, retained elements, return
values and interface operations. A growing set of attributes can become a less
uniform lifetime language. A general contract notation could cover several
relations, but explicit lifetime parameters make those relationships part of
ordinary types and generic composition. Ordinary callers still infer arguments.

RFC 0004 owns signature stability, elision, bounds, variance, quantified
callables and compatibility. This RFC retains the storage/flow invariants,
subject to those type rules. In particular, mutable access cannot reinterpret a
container's element lifetime to admit a shorter-lived value. A helper with
explicitly unrelated regions is rejected unless its declared bounds establish
the required relation; body inference does not override that signature.

Sequencing:

- RFC 0004 must be accepted and the relevant contract/type prerequisites
  available before M3; its typed-storage ownership and drop obligations also
  gate M4. Co-development may be planned only after the corresponding designs
  are accepted.
- M0-M2 may be considered as independently authorized, validated groundwork.
  Their scope must not ship the abandoned attribute surface or claim that this
  dependent RFC is complete.
- M3 onward uses the common lifetime model. No new public `stores` or
  `stores_borrows` attribute is staged as an interim feature.

The original open decision and inferred-attribute sketch remain in repository
history; the decision record below preserves why this draft changed direction.

### Other alternatives

**Keep the current behavior.** Users keep cloning or storing offsets. This is safe
and simple, but it leaves a common systems pattern slower or less direct than in
Rust.

**Construction-fixed owner containers.** A container bound to one owner when
built, such as `view_list(text)`, checks that each pushed view belongs to that
owner. This needs no widening and fits the current carrier model. It covers the
single-source tokenizer but not generic `std::vector<T>` or multi-source data, and
it risks a container-specific rule. It is a credible cheaper fallback.

**Hidden region variables in types.** Give `std::vector<std::string_view>` an
invisible region inferred by the compiler. This has the power of lifetimes with no
syntax, but it would produce diagnostics about things users cannot name, and it
has the same boundary problem.

**Reference-counted views.** A view that keeps its owner alive at runtime removes
the static problem at the cost of a count per view. That is a different feature,
and it contradicts the zero-cost goal for this case.

**Interning and index handles.** Useful library patterns, available today, which
remain valid. They do not provide the general capability.

## Unresolved questions

1. **Prerequisite readiness:** which accepted/implemented RFC 0004 slices
   provide the type, interface and storage contracts needed by M3/M4? The
   dependency is selected; acceptance of either complete design is pending.
2. **Exported API migration:** apply RFC 0004's stable contracts to existing
   body-inferred APIs and verify callers do not depend on hidden body precision.
3. **Phase split:** which part of the set computation runs in semantic flow
   analysis, and which only in the MIR fixed point?
4. **Granularity:** one set per root, or one per type parameter, so that a
   `map<K, V>` with two borrowed parameters can release them separately? Does
   `L-UP-16` projection precision compose with this?
5. **Cleanup facts:** how does the common model prove BC-8 for passive element
   cleanup versus borrow-observing destructors? No unchecked `may_dangle` escape
   is implied; opaque cleanup is conservative under RFC 0004.
6. **Unsafe discharge through helpers:** `construct_value_at` takes a raw `T*`,
   which cannot establish ownership under BC-11. What typed owner/witness and
   drop metadata must its caller and low-level helpers preserve?
7. **Exclusive elements:** what is the path to `Vec<&mut T>`-like storage, given
   that dynamic-index identity is not modeled?
8. **Text unification:** should the single-owner text model be replaced first, or
   can sets be introduced alongside it for a transition?
9. **Admission query:** what should the structural query replacing
   `is_borrow_free` in `storage_element` be called and promise?
10. **Scope of closed boundaries:** how soon must stored-reference targets (BC-16)
    open for real programs?

## Implementation plan

Slices are ordered so that each one is useful alone. No slice is implemented, and
this plan is not an authorization to start.

| Slice | Content | Depends on |
| --- | --- | --- |
| M0 | Treat a raw store of a text formal as a "requires ownerless" contract, so literal views enter containers. May land as an ordinary fix. | Nothing |
| M1 | Dependency sets for local bindings: strong and weak updates, joins, reseating local views; multi-owner text | Phase split decision |
| M2 | Fixed arrays of shared carriers (static size, no growth) | M1 |
| — | **Prerequisite gate: RFC 0004.** Accepted lifetime design and relevant type/interface prerequisites available | RFC 0004 L0-L4 as applicable |
| M3 | Body-flow summaries checked against RFC 0004 lifetime-bearing declarations and stable call contracts | M1, RFC 0004 gate |
| M4 | Tracked storage, BC-12 reads, cleanup proofs and shared `std::vector` admission in one coherent change | M3, RFC 0004 LT-8/L5 storage contract |
| M5 | Associative containers: `std::hashing` and ordering for `string_view`, map and set admission | M4 |
| M6 | Containers in fields and returned containers, multi-origin results | M4 |

Later proposals: exclusive elements, stored-reference targets, heterogeneous
lookup. Implementation tracking belongs in the GTI repository and links back here.

## Validation and release criteria

Positive cases: each guide-level program, run with cleanup checks; a borrow stored
in a loop over a range; `v.push_back(v[0])`; an explicit lifetime helper and its
inferred calls; eligible private/recursive helper inference; failure during
`push_back`; moved, cloned and swapped carriers;
a container declared before its owner.

Negative cases: mutation, move and destruction of an owner while the container is
live; a store through a mutable reference alias followed by owner invalidation; a
value leaving by `pop_back` and outliving its owner; a local's view stored through
a formal; self-dependency; stores to globals, captures and threads; a false
contract on a safe body; unrelated explicit lifetimes at insertion; mutation
through an invariant container reference; a container of elements whose
destructors read the dependency, declared before its owner.

Generality: an unrelated user-defined container and carrier must reach all of the
above without compiler knowledge of `std::vector`, `std::string_view` or
`std::unordered_map`.

Comparison evidence: the table below records `rustc` 1.99.0 behavior for analogous
programs. It is useful as a cross-check of expected outcomes. Rust is not GTI's
specification, and differences may be deliberate.

| Program | rustc | Expected here |
| --- | --- | --- |
| `add<'a>` helper called from a loop, two owners | Accepted | Accepted |
| Container declared before its owner, passive drop | Accepted | Accepted |
| Same, element with a `Drop` that reads the borrow | `E0597` | Rejected |
| `clear()` then owner mutation, container used after | `E0502` | Rejected |
| Whole-value replacement then owner mutation | Accepted | Accepted |
| Copy an element out, push it back | Accepted | Accepted |
| Helper pushing an explicitly unrelated lifetime | Rejected | Rejected unless the declared lifetime bounds permit the store |
| Two `&mut` to distinct owners in one `Vec` | Accepted | Deferred |
| Two `&mut` to one owner | `E0499` | Deferred |

Performance: the workloads above, with compile-time and editor latency compared
against a recorded baseline. Tooling: LSP diagnostics with related locations,
formatter and Tree-sitter coverage for any new syntax, on LLVM. Documentation:
update the ownership, standard-library and concepts specifications, add examples,
and update the plan rows. Compiler validation follows the GTI repository's policy.
Document checks here establish none of this.

## Decision record

No complete design has been accepted.

- **2026-11-06, initial draft:** the owner asked that lifetime syntax be recorded
  as a possible prerequisite with a separate RFC. The original draft left that
  decision open and explored an inferred surface with store attributes.
- **2026-11-06, subsequent owner direction:** the owner selected the illustrated
  `lifetime a` / `T&<a>` form, asked for an inference/elision-first lifetime RFC,
  and explicitly requested that this RFC depend on it. This revision therefore
  names [RFC 0004](0004-lifetime-parameters-and-elision.md) as the prerequisite
  and replaces the proposed store-attribute surface with its common contracts.
- **Pending:** acceptance of the complete lifetime and container designs,
  resolution of their remaining proof obligations and authorization of any
  implementation work. Storing these drafts in the catalog is not acceptance.

## References

- [RFC 0004: Lifetime parameters with inference and elision](0004-lifetime-parameters-and-elision.md): required lifetime/type-contract foundation; this RFC owns its dynamic storage consumer.
- [Ownership, references and allocation](https://github.com/lang-gti-official/gti/blob/4c71f55c9c560ae6830829cd9ca466087d9bbe8c/docs/language/ownership-and-lifetimes.md): current carrier, view-field and rejection rules.
- [Concepts](https://github.com/lang-gti-official/gti/blob/4c71f55c9c560ae6830829cd9ca466087d9bbe8c/docs/language/concepts.md): `borrowed_from`, `is_borrow_free`, and the multi-origin follow-up.
- [Standard library](https://github.com/lang-gti-official/gti/blob/4c71f55c9c560ae6830829cd9ca466087d9bbe8c/docs/language/standard-library.md): container and owned-key contracts.
- [Place and ownership state](https://github.com/lang-gti-official/gti/blob/4c71f55c9c560ae6830829cd9ca466087d9bbe8c/docs/plans/place-and-ownership-state.md): place, epoch and reseating foundations.
- [Language alignment](https://github.com/lang-gti-official/gti/blob/4c71f55c9c560ae6830829cd9ca466087d9bbe8c/docs/plans/language-alignment.md): the `R-*` rows named above.
- [MIR](https://github.com/lang-gti-official/gti/blob/4c71f55c9c560ae6830829cd9ca466087d9bbe8c/docs/architecture/mir.md): carrier storage versus stored dependency.
- [ADR 018](https://github.com/lang-gti-official/gti/blob/4c71f55c9c560ae6830829cd9ca466087d9bbe8c/docs/decisions/018-loan-erasure-representation.md): loans erase, so no runtime representation is needed.
- [RFC 0002 proposal](https://github.com/lang-gti-official/rfcs/pull/2): borrow-checker verification, which this work should feed.
- [Rust RFC 2094, non-lexical lifetimes](https://rust-lang.github.io/rfcs/2094-nll.html): last-use endpoints and flow-sensitive liveness.
- [Rustonomicon: subtyping and variance](https://doc.rust-lang.org/nomicon/subtyping.html): why `&mut Vec<&'a T>` is invariant.
- [Rustonomicon: drop check](https://doc.rust-lang.org/nomicon/dropck.html): the `may_dangle` precedent for BC-8.
- [Rustonomicon: PhantomData](https://doc.rust-lang.org/nomicon/phantom-data.html): the precedent for declaring what raw storage holds.
