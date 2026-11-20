# RFC 0008: Chrono duration units and checked conversions

| Field | Value |
| --- | --- |
| Status | draft |
| Authors | Luke Howe |
| Created | 2026-11-20 |
| Updated | 2026-11-20 |
| Area | stdlib |
| Proposal | pending |
| Decision | pending |
| Implementation | none |
| Supersedes | none |
| Superseded by | none |

## Summary

Extend `std::chrono` with strongly typed microseconds, milliseconds, seconds,
minutes, and hours alongside existing nanoseconds. Add explicit checked
`duration_cast<To>()` conversions. Integer conversions truncate toward zero;
overflow returns an error. This is a proposed API, not an implemented feature.

## Motivation and goals

Programs currently express time in nanoseconds and manually scale counts for
configuration, reporting, and elapsed-time calculations. The current chrono
module deliberately provides a bounded nanosecond-only slice. This proposal
extends that slice without changing clocks or requiring a complete C++ chrono
implementation.

Success means applications can express their intended units directly, convert
without handwritten scale constants, and detect unrepresentable results. A large
hours value should remain representable even when its nanosecond equivalent is
not.

## Non-goals

Calendar units, dates, time zones, formatting, sleeping, user-defined literals,
floating-point representations, implicit cross-unit conversions, mixed-unit
arithmetic, clock arithmetic extensions, and a general rational-number library
are outside this proposal. Exact conversion and floor/ceil/round helpers can be
proposed separately.

## Guide-level design

C++ models a duration as a count and a compile-time period in seconds. Its named
units are specializations of `duration<Rep, Period>`. GTI should adopt the count
and unit model while initially exposing six named integer duration types.

Proposed usage inside a function returning a compatible `expected`:

```gti
import std.chrono;

auto elapsed = std::chrono::milliseconds{int64_t(1500)};
auto whole_seconds = ?std::chrono::duration_cast<std::chrono::seconds>(elapsed);
// whole_seconds.count() == 1

auto backwards = std::chrono::milliseconds{int64_t(-1500)};
auto backwards_seconds = ?std::chrono::duration_cast<std::chrono::seconds>(backwards);
// backwards_seconds.count() == -1

auto timeout = std::chrono::minutes{int64_t(2)};
auto timeout_ms = ?std::chrono::duration_cast<std::chrono::milliseconds>(timeout);
// timeout_ms.count() == 120000
```

Each type offers a zero-initializing default constructor, an explicit construction
from an `int64_t` tick count, and `count()` returning that count. Cross-unit
construction is not implicit. The examples require implementation of this RFC.

The proposed conversion result is `expected<To, duration_errc>` with
`duration_errc::out_of_range`. Callers may propagate or inspect failure. A result
that discards a fractional tick is successful; only an unrepresentable destination
count is an overflow error. For example, converting the maximum signed 64-bit
hours count to minutes fails, while converting it to hours succeeds unchanged.

## Semantic rules

| Type | Tick in nanoseconds | Representation |
| --- | ---: | --- |
| nanoseconds | 1 | int64_t |
| microseconds | 1000 | int64_t |
| milliseconds | 1000000 | int64_t |
| seconds | 1000000000 | int64_t |
| minutes | 60000000000 | int64_t |
| hours | 3600000000000 | int64_t |

Every duration stores its own tick count, not a normalized nanosecond count.
Units are distinct types. The conversion operation accepts only supported
duration types and returns a new destination value without modifying or retaining
the source. Source expressions are evaluated once; ordinary GTI borrowing and
temporary-borrow rules apply. No pointers or borrows escape the conversion.

For source count `n` and tick sizes `S` and `D`, the mathematical result is
`truncate_toward_zero(n * S / D)`. The implementation must reduce the ratio before
performing arithmetic. For these six units one reduced factor is always one:
identity is a copy, coarsening is division, and refinement is checked
multiplication. Overflow is determined by the final destination count, not an
avoidable intermediate. Do not convert through nanoseconds or take `abs(n)`;
both would incorrectly reject valid boundary values or overflow at `INT64_MIN`.

Negative durations are valid. Division toward zero is deliberate: -1500 ms
becomes -1 s. This does not change `system_time_point::unix_seconds()`, whose
existing floor-based epoch decomposition serves a different purpose.

Construction, count access, and checked conversions should be `constexpr` using
GTI's existing constant-evaluation machinery, with identical runtime semantics.
Overflow produces an error value even during constant evaluation; callers still
choose how to handle that result.

## Compiler and tooling design

Implement the feature primarily in `stdlib/std/chrono.gti`, reusing the checked
integer operations in `std.numeric`. Prefer shared source-defined conversion
logic and ordinary generic constraints. Do not add hard-coded chrono names or
unit conversions to the compiler.

Preserve `nanoseconds` compatibility while deciding whether the shared internal
representation should be a private generic type or several small nominal types.
A public `duration<Rep, Period>` and ratio protocol are deferred unless review
establishes a concrete need within this scope.

Before implementation, check that the chosen source representation and generic
constraints work with existing constexpr support. Any missing general capability
must be recorded as a prerequisite, not implemented through chrono-specific
exceptions. Constant evaluation remains staged verified MIR, with LLVM as the
primary backend; no parallel AST evaluator is proposed.

No grammar, formatter, driver, or runtime service changes are expected. LSP
completion, hover, and definition should discover the exported source APIs through
normal mechanisms. Unsupported source/destination types should receive ordinary
generic-constraint diagnostics at the call site. Documentation generation must
expose each named unit and the conversion function.

## Compatibility and migration

Existing `nanoseconds` construction and `count()` retain their behavior. Clocks,
time points, elapsed-time methods, and their current error types/signatures remain
unchanged. Applications opt in by constructing named units and explicitly casting
existing nanosecond results.

Update the current chrono specification's exclusions to permit these six units
and checked explicit conversions while retaining the remaining bounded scope.
Do not change floor-based Unix timestamp decomposition to match duration casting.
If generic aliases would change source-visible type identity or tooling output,
preserve the existing nominal type instead or resolve that compatibility issue
before acceptance.

## Safety and correctness

Conversions require no unsafe code, allocation, OS access, or cleanup resources.
All signed multiplication must be checked before evaluating an overflowing
operation. Division factors are positive nonzero constants. Preserve signed
minimum and maximum counts in identity conversions, and never negate the minimum
count to implement truncation. Error paths must return no partial destination.

The conversion test matrix and boundary tests establish evidence for the finite
six-unit contract. They do not establish correctness of an arbitrary future ratio
implementation, which would require additional reasoning and tests.

## Performance and resource costs

The intended storage is one signed 64-bit count per duration, without a runtime
unit tag or heap allocation. Each specialized conversion should compile to a
copy, division by a constant, or checked multiplication by a constant. The
`expected` return value carries error handling; checks must not be removed merely
to match unchecked C++ casts.

These are design expectations, not measurements. During implementation inspect
optimized LLVM output for representative casts and compare configuration-time
and repeated elapsed-time conversions against equivalent checked integer code.
Record compile-time/code-size impact of generic instantiations, and avoid emitting
all 36 conversions in programs that use only a few.

## Alternatives and tradeoffs

- Keep nanoseconds only: minimal API, but every caller continues to duplicate
  scale constants and overflow handling.
- Store every duration as nanoseconds: simple sharing, but destroys the wider
  useful range of hours and minutes. Rejected for the proposed contract.
- Implement full C++ `duration<Rep, Period>` now: supports arbitrary ratios and
  representations, but brings more conversion, common-type, arithmetic, and
  overflow policy questions than these units require. Defer that public surface.
- Permit implicit widening conversions as C++ does: convenient, but a finer
  destination unit can overflow even without fractional loss. Explicit checked
  conversions keep this failure visible.
- Reject fractional results: useful for exact configuration validation, but the
  user explicitly selected truncation toward zero as the default.
- Reuse `clock_errc::out_of_range`: less API growth, but couples pure duration
  conversion to clock availability errors. A dedicated duration error is the
  recommendation, pending review.

## Unresolved questions

1. Confirm `duration_errc::out_of_range` rather than reusing `clock_errc`.
2. Confirm the initial public surface is six named types, with any generic
   representation private; decide its precise source representation after a
   small compiler-capability audit.
3. Confirm whether same-unit comparison operators belong in this first increment
   or a separate arithmetic proposal. They are not required by the conversion
   contract and are excluded from the proposed minimum scope.

Truncation toward zero is a user-selected rule. Full generic ratios, floating
representations, arithmetic, and rounding helpers are deferred follow-up work,
not hidden prerequisites to shipping the named units.

## Implementation plan

1. Resolve the public error/type surface and verify existing generics and staged
   constexpr capabilities against the chosen representation. Record any general
   compiler prerequisite before expanding scope.
2. Add the five new unit types and shared checked conversion logic, preserving
   nanoseconds and clock APIs. Keep units strongly typed and source-defined.
3. Add focused constexpr/runtime conversion tests, boundary and constraint tests,
   and existing clock regression coverage. Inspect optimized conversion code.
4. Update canonical chrono docs, a runnable duration example, and standard-library
   inventories as needed. Update the reference website with discoverable unit
   documentation and an individual `duration_cast` page, using its authoring
   rules. Link implementation PRs here only when actual work begins.

No implementation has been started by this proposal, and no release date is
promised. Implementation will use the compiler repository's current workflow.

## Validation and release criteria

Test all 36 source/destination pairs with zero, positive, and negative counts.
Test discarded fractions on both signs, exact multiples, identity at signed
minimum/maximum, and widening values immediately inside and outside each safe
boundary. Include an hours-to-minutes value whose result fits while converting
through nanoseconds would overflow. Check one source evaluation and source
preservation.

Verify constexpr/runtime agreement for successful and failing conversions.
Reject unrelated types and implicit cross-unit conversions. Run existing chrono
clock/elapsed tests, especially negative Unix timestamps. Verify normal LSP API
discovery and generated reference links/examples. Validate optimized LLVM output
and storage/allocation expectations on supported implementation targets.

Use focused checks while developing and the implementation repository's release
policy before shipping. For this document, only regenerate/check the RFC index
and run whitespace checks. Passing document checks is not compiler validation,
design acceptance, or release readiness.

## Decision record

The owner requested planning only on 2026-11-20 and selected integer conversion
truncation toward zero, matching C++ duration_cast. This records a planning input,
not acceptance of the complete API. No acceptance decision or implementation
exists; a durable owner decision must be linked before changing draft status.

## References

- [Current chrono source](https://github.com/lang-gti-official/gti/blob/29a7a1bb1f9fb0f051f364835bd1336214f09682/stdlib/std/chrono.gti): existing nanoseconds, clocks, time points, and error behavior.
- [Current chrono specification](https://github.com/lang-gti-official/gti/blob/29a7a1bb1f9fb0f051f364835bd1336214f09682/docs/language/chrono.md): bounded scope and timestamp semantics this proposal extends.
- [Current chrono tests](https://github.com/lang-gti-official/gti/blob/29a7a1bb1f9fb0f051f364835bd1336214f09682/tests/ui/stdlib/chrono/chrono.gti): existing regression behavior.
- [Implementation sequence, L-CONST-01](https://github.com/lang-gti-official/gti/blob/29a7a1bb1f9fb0f051f364835bd1336214f09682/docs/plans/implementation-sequence.md): staged MIR constant-evaluation architecture.
- [C++ duration](https://eel.is/c++draft/time.duration): count/period model and named-unit precedent.
- [C++ duration_cast](https://eel.is/c++draft/time.duration.cast): explicit ratio conversion and separate rounding operations.
