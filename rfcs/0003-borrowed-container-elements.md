# RFC 0003: Borrowed elements in containers

| Field | Value |
| --- | --- |
| Status | draft |
| Authors | @gti-language-official (with Claude) |
| Created | 2026-11-06 |
| Updated | 2026-11-06 |
| Area | language |
| Proposal | pending |
| Decision | pending |
| Implementation | none |
| Supersedes | none |
| Superseded by | none |

## Summary

Let checked borrows live inside containers, so that
`std::vector<std::string_view>` over local strings and
`std::unordered_map<std::string_view, int>` compile and stay memory safe, with
no runtime cost and no change to how a view is represented.

The core change is one rule: a value's dependency set may **grow after
construction**. Today a carrier's owners are fixed when it is built. Under this
proposal, storing a borrowed value into an existing owner adds that value's
dependencies to the owner, and every added owner stays protected until the
container's last use. Function summaries carry the same fact across calls, and a
trusted boundary lets source-defined storage declare what it holds.

**Lifetime syntax is an open prerequisite decision.** This draft specifies the
semantic model and sketches an inferred surface with one small contract
attribute. That surface may prove inadequate. The owner may decide that explicit
lifetime syntax is a prerequisite to this RFC, and lifetimes may receive an RFC
of their own, which this one would then depend on. The semantic rules here are
written so that they hold under either outcome; see
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
- **Deciding lifetime syntax here.** This RFC records the decision point and its
  consequences. If lifetimes are pursued, their syntax, variance, elision and
  type-system rules belong to a separate RFC.
- **Heterogeneous lookup.** A `Borrow`-style query that finds a `std::string` key
  from a `string_view` is a separate library proposal, though it is useful
  beside this work.
- **New allocation or container redesign.** `R-ASSOCIATIVE-CONTAINERS`
  follow-ups stay separate.

## Guide-level design

All examples in this section require this proposal unless marked otherwise. The
attribute spelling is a placeholder under the inferred surface.

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

A helper needs no annotation when its body is available:

```gti
void remember(mut std::vector<std::string_view>& out, std::string_view word) {
  out.push_back(word);   // inferred summary: word flows into out
}
```

A declaration with no visible body needs a contract, because the compiler cannot
read what it does:

```gti
concept view_sink<S> = requires(mut S& sink, std::string_view word) {
  { sink.add(word) } -> void [[stores(word, sink)]];
};
```

A trusted owner declares what its unsafe code does, and safe wrappers above it
are inferred:

```gti
[[stores(value, this)]]
unsafe void append_value_unchecked(T value) mut { ... }
```

Under an explicit lifetime surface, the same helper would instead say which
dependencies are related, in some form such as the following. **This spelling is
illustrative only and is not proposed here.**

```gti
void remember<'a>(mut std::vector<std::string_view<'a>>& out, std::string_view<'a> word);
```

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

**BC-1. Dependency sets are per-point facts.** `D(b)` is a flow-sensitive
compile-time fact, not part of `b`'s type and not runtime state.

**BC-2. A retaining store widens.** Storing `x` into a place under root `b` sets
`D(b) := D(b) ∪ D(x)`. This includes a store through a mutable reference whose
exact origin is known, and an element write through a mutable subscript. A
reference that may select among several roots widens every candidate.

**BC-3. Whole-value replacement narrows.** Assigning to an exact local binding
with no live reborrow sets `D(b) := D(x)`, after the old value's cleanup. A store
through a reference is always a widening. Operations such as `clear`, `erase` or
`pop_back` do not narrow.

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

**BC-9. Flow summaries.** A function's summary lists edges `source -> target`,
where `source` is a formal and `target` is a formal's referent or the receiver.
At a call, each edge applies BC-2 to the actual arguments. Summaries are derived
from concrete bodies as a least fixed point over recursive sets, following the
existing text contract approach. A local's dependency reaching a target is an
escape and is rejected in the callee.

**BC-10. Declared contracts.** Where no body can be read, namely virtual calls,
concept operations and erased callables, a store requires a declaration. Absent
one, the current rule applies: the argument must be ownerless. A safe body's
derived summary must be a subset of what it declares. Multi-origin result
contracts, already recorded as a follow-up in the concept specification, extend
`[[borrowed_from]]` in the same way so that a returned container can depend on
several formals. Which surface expresses these contracts is the
[prerequisite decision](#prerequisite-decision-lifetime-syntax).

### Storage and unsafe code

**BC-11. Tracked storage.** A raw store of a dependency-carrying value stays
rejected outside an unsafe function that declares a matching store contract.
Inside one, unsafe code may place the value in raw memory, and the author takes
on the obligation that the declaration is truthful. Safe code above it is
inferred through ordinary composition, so only the lowest storage layer declares
anything. Target `this` or a formal only: a raw pointer cannot be a target,
because it has no tracked origin.

**BC-12. Reads from tracked storage are never ownerless.** A result of a
dependency-capable type produced by an unsafe body inherits every input's
dependencies unless a contract narrows it. This matters because
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
| Parser, AST, grammar | Contract syntax under whichever surface is chosen |
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

The change is additive. Programs that compile today keep their meaning, because
each admitted shape is rejected today. Rejections that move or change wording
need test updates.

This proposal revises several recorded boundaries, which stay in place until a
decision changes them:

- `ownership-and-lifetimes.md`: "arrays of borrowed carriers ... and assignment
  that would replace a carrier's dependency remain rejected".
- `implementation-sequence.md`: dynamic text views reject "reassignment/reseating
  and storage in globals, fields, fixed arrays, or dynamic storage", and
  associative containers do "not admit borrowed-state container elements".
- `place-and-ownership-state.md` section 10 on dependency-reseating assignment.
- The concepts specification's single-origin requirement result.

It may also revise "No source lifetime parameters are introduced" in
`ownership-and-lifetimes.md`, if the prerequisite decision goes that way. That
would be a separate decision with its own RFC, not a side effect of this one.

Inferred summaries make a function body part of its callers' checking. Editing a
body can break a caller with no signature change. Existing inferred text
contracts already behave this way, but containers make it far more common.

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
- **Unsafe contracts:** a false `stores` declaration breaks containment. This is a
  trusted obligation, so the set of declaring functions should stay small and
  audited.
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

This is the largest open design question. It may be decided that explicit
lifetime syntax is a **prerequisite** to this RFC, and lifetimes may end up with
**an RFC of their own**, which this RFC would then depend on.

The pressure comes from function boundaries. In a body, dependency sets can be
inferred. At a boundary with no readable body, the relationship must be written
down somewhere, and a growing list of boundary needs points toward a general
notation:

- argument to receiver (`stores`);
- result from several inputs (multi-origin `borrowed_from`);
- two containers sharing an element dependency;
- concept operations, virtual calls and erased callables;
- stable public APIs, where a body edit must not silently change a contract;
- element dependencies in a signature, such as a function returning
  `std::vector<std::string_view>` whose owners matter to callers.

Rust states all of these with one mechanism, because the lifetime is part of the
type: `fn add<'a>(v: &mut Vec<&'a str>, s: &'a str)`. Each attribute above is a
special case of that relation, so a growing attribute set may end up as a worse
lifetime system.

| | Inferred sets with contract attributes | Explicit lifetime syntax |
| --- | --- | --- |
| Ordinary code | No annotations | Elision would need to cover common cases |
| Boundaries | One attribute per relation shape | One general notation |
| Public API stability | Body edits can change inferred contracts | Signature states the contract |
| Generics | Dependency is invisible to `T` | Can appear in the type |
| Language surface | Small at first, may grow | Large, and affects types, generics and the existing "no lifetime parameters" position |
| Existing code | Unaffected | Depends on elision and defaults |

What survives either outcome: the semantic rules BC-1 to BC-8 and BC-11 to BC-16
describe what a borrow in a container means. Lifetime syntax would replace how
relations are **declared** (BC-9 and BC-10), and could reframe BC-1 by moving part
of the fact into types. It would also add variance, which the inferred surface
avoids and which Rust needs here: `&mut Vec<&'a str>` is invariant in `'a`, so a
helper that pushes an unrelated `&'b str` is rejected.

The consequences for sequencing are:

- **If lifetimes are decided to be a prerequisite:** this RFC waits for that RFC
  to be accepted. M0 to M2 of the implementation plan do not touch declarations,
  so they can still proceed if the owner wants them to. M3 onward is rewritten
  against the lifetime design, and the `stores` attribute is dropped.
- **If they are not:** this RFC proceeds with the inferred surface, and the
  attribute set stays small and closed.
- **If undecided at M3:** implementation stops there rather than shipping an
  attribute that a later lifetime design would have to deprecate.

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

1. **Lifetime syntax:** is it a prerequisite, and does it get its own RFC? This
   gates M3 onward and is the first decision to make.
2. **Exported APIs:** if inference stays, must exported functions declare their
   summaries so that a body edit cannot silently break callers?
3. **Phase split:** which part of the set computation runs in semantic flow
   analysis, and which only in the MIR fixed point?
4. **Granularity:** one set per root, or one per type parameter, so that a
   `map<K, V>` with two borrowed parameters can release them separately? Does
   `L-UP-16` projection precision compose with this?
5. **Cleanup facts:** can BC-8 always be inferred from concrete instances, or does
   an unsafe owner need a declaration like Rust's `may_dangle`?
6. **Unsafe discharge through helpers:** `construct_value_at` takes a raw `T*`,
   which cannot be a contract target under BC-11. Does the discharge pass through
   unsafe helpers, or must the store sit directly in the declaring function?
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
| — | **Decision gate: lifetime syntax.** Resolve question 1 before M3 | Owner decision |
| M3 | Flow summaries and declared contracts, or their lifetime equivalent | M1, gate |
| M4 | Tracked storage, BC-12 read rule, `std::vector` admission, shared in one change | M3 |
| M5 | Associative containers: `std::hashing` and ordering for `string_view`, map and set admission | M4 |
| M6 | Containers in fields and returned containers, multi-origin results | M4 |

Later proposals: exclusive elements, stored-reference targets, heterogeneous
lookup. Implementation tracking belongs in the GTI repository and links back here.

## Validation and release criteria

Positive cases: each guide-level program, run with cleanup checks; a borrow stored
in a loop over a range; `v.push_back(v[0])`; a helper with an inferred summary; a
recursive helper; failure during `push_back`; moved, cloned and swapped carriers;
a container declared before its owner.

Negative cases: mutation, move and destruction of an owner while the container is
live; a store through a mutable reference alias followed by owner invalidation; a
value leaving by `pop_back` and outliving its owner; a local's view stored through
a formal; self-dependency; stores to globals, captures and threads; a false
contract on a safe body; a container of elements whose destructors read the
dependency, declared before its owner.

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
| Helper pushing an unrelated lifetime | Rejected | Accepted with a summary under inference; depends on the lifetime decision |
| Two `&mut` to distinct owners in one `Vec` | Accepted | Deferred |
| Two `&mut` to one owner | `E0499` | Deferred |

Performance: the workloads above, with compile-time and editor latency compared
against a recorded baseline. Tooling: LSP diagnostics with related locations,
formatter and Tree-sitter coverage for any new syntax, on LLVM. Documentation:
update the ownership, standard-library and concepts specifications, add examples,
and update the plan rows. Compiler validation follows the GTI repository's policy.
Document checks here establish none of this.

## Decision record

No design decision yet. On 2026-11-06, while this draft was being written, the
owner observed that lifetime syntax increasingly looks unavoidable and asked that
this RFC record that lifetime syntax may be decided to be a prerequisite, and that
lifetimes may receive their own RFC. That is direction for this draft, not an
acceptance of either outcome.

## References

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
