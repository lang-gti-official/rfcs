# RFC 0009: Calendar time, time zones and temporal formatting

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

Extend `std::chrono` with validated Gregorian dates, civil times, calendar arithmetic, wide Unix timestamps, immutable IANA time-zone data, explicit daylight-saving resolution, and checked temporal formatting. Build on RFC 0008's duration family rather than replacing it. This is a proposed library design, not an implementation claim.

Keep three meanings distinct: an elapsed duration, a local calendar reading, and an instant on the timeline. A day as a duration is exactly 86,400 seconds; advancing a local calendar day preserves the clock reading and may cross an offset change. Months and years are calendar counts, not durations convertible to seconds without a starting date and zone.

The audit indicates predominantly standard-library and data-distribution work. No broad compiler refactor is proposed. Small feasibility probes must confirm the exact generic, literal-validation and ownership combinations before acceptance.

## Motivation and goals

Applications need to display the current date/time, calculate expiration instants, schedule local appointments, name dated files, and interpret timestamps in a named zone. These are general capabilities, independent of any one application.

Audit baseline: GTI main commit `8baa0081bf95afa37b06dec28fffa48c06249774`, with the separately identified dependency PR #647 at `f7dac0ea55042d8aba130cb95941af624296d827`. At audit time #647 was open, not merged.

| Audited capability | Consequence for this design |
| --- | --- |
| Main `stdlib/std/chrono.gti`: nanosecond durations, steady/system clocks, Unix decomposition; no calendar or zone API | Add calendar and zone layers; retain existing clock contracts. |
| PR #647: `duration<Unit>`, six unit aliases, checked arithmetic, `try_cast`/`cast`, truncation toward zero | Reuse this pending foundation; add fixed `days`. Do not claim these additions are already on main. |
| Structural requirements, constexpr constraint predicates, protocol concepts and generic conformances | Express duration eligibility and default formatting without compiler recognition of chrono types. |
| Protocol associated types/type families, but no associated constants/value families | Avoid a design dependent on trait-associated numeric constants. Use existing instance metadata methods for units. |
| Constexpr arithmetic, records, control flow and expected values | Date validation and calendar conversion can be constexpr. Zone discovery/file access cannot. |
| Checked immediate arguments and implicit consteval construction | Reuse the existing checked-pattern approach for literal temporal formats. |
| Payload enums and exhaustive switching | Represent unique, ambiguous and nonexistent local-time mappings explicitly. |
| Region-aware borrows and move-only owning values | Keep references tied to owners; do not return dangling views into a temporary database. |
| `std::shared_ptr<T>` with explicit `clone()` and conditional thread capabilities | Own immutable zone rules across database destruction/reload. Actual payload capabilities still require verification. |
| `expected` and registered `std::from` error propagation | Report invalid dates, ambiguous times, data failures and overflow without exceptions. |
| `std::formatting<T>` receives a fixed `format_spec`, not arbitrary pattern text | Use that protocol for default output; provide a dedicated chrono pattern API for custom layouts. |
| Byte spans, file IO, modules and embedded bytes | Implement a source-defined checked TZif reader and optional pinned data bundles. |
| Macros, reflection and structured bindings | Useful elsewhere, but unnecessary prerequisites for calendar correctness. No new literal suffix syntax is needed. |

Success means ordinary applications can format a current zoned time, select explicit DST behavior, and do both elapsed and calendar arithmetic without native interop or accidental unit conversions.

## Non-goals

- Leap-second-aware UTC/TAI/GPS timescales, astronomical or non-Gregorian calendars.
- Full locale/CLDR integration, natural-language date parsing, recurring-schedule engines, or a general date-string parser.
- New language operators, user-defined numeric suffixes, or a redesign of `std::format`'s format-spec protocol.
- Automatically downloading time-zone updates or changing the process-global `TZ` setting.
- Replacing monotonic clocks for timeouts, benchmarking or elapsed measurements.

## Guide-level design

All examples below are proposed APIs. They have not been compiled or implemented.

### Types and units

| Type | Meaning |
| --- | --- |
| `seconds`, `minutes`, `hours`, `days` | Signed fixed durations; `days(1)` is exactly 86,400 seconds. |
| `calendar_days`, `months`, `years` | Signed calendar step counts; no implicit conversion to fixed durations. |
| `date` | Valid Gregorian date, initially years 1 through 9999. |
| `time_of_day` | Valid hour/minute/second/nanosecond reading. |
| `local_datetime` | A date and clock reading, with no assumed zone. |
| `timestamp` | Unix instant represented by seconds plus normalized nanoseconds. |
| `time_zone` | UTC, a fixed offset, or an immutable named-zone rule handle. |
| `zoned_time` | An instant plus an owned zone handle and validated local representation. |
| `tzdb` | An immutable, versioned collection of named-zone data. |

Do not add two timestamps. Add a duration to an instant, subtract instants to obtain a checked duration, or advance a calendar reading using calendar counts.

### Displaying the current time

```gti
import std.chrono;
import std.format;

namespace c = std::chrono;

expected<void, c::error> show_now() {
  auto db = ?c::tzdb::load_default();
  auto perth = ?db.locate("Australia/Perth");
  auto now = ?c::timestamp::now();
  auto local = ?perth.at(now);
  auto text = ?c::try_format(local, "%I:%M:%S %P on %d %b %Y");
  std::println("{}", text);
  return;
}
```

For the corresponding reading, that pattern produces `10:30:33 am on 20 Nov 2026`. It does not change the instant or the machine's zone. The proposed umbrella `chrono::error` preserves component causes through explicit `std::from` conformances.

### Calendar arithmetic and DST

```gti
auto january = ?c::date::create(2027, 1, 31);
auto rejected = january.try_add(c::months(1)); // invalid resulting date
auto february = ?january.try_add(c::months(1), c::month_roll::clamp);

auto appointment = ?c::local_datetime::create(2026, 11, 20, 10, 30, 33);
auto meeting = ?perth.resolve(appointment); // rejects ambiguity/gaps by default
```

`date` and `local_datetime` offer `try_add(calendar_days)`, `try_add(months, month_roll)` and `try_add(years, month_roll)`. `timestamp::try_add(duration)` performs elapsed arithmetic. To advance a zoned appointment by a calendar day, get its local reading, advance it, then resolve it in the same zone with an explicit policy. This intentional composition makes DST handling visible.

`zone.lookup(local)` returns an expected payload enum: unique instant, ambiguous earlier/later instants, or nonexistent-time gap information. `zone.resolve(local, policy)` provides the common selection operation. The default rejects ambiguity and gaps; options select the earlier/later instant for a fold or the next valid reading for a gap. “Next valid” means the transition boundary, not preserving minutes by shifting a whole gap. A separate shift policy can be considered later.

## Semantic rules

### Validated calendar values

Constructors validate components and return `expected`. Fields are private; successful values are always valid. Calendar math is proleptic Gregorian, independent of locale and zone. Years 1–9999 are the recommended initial public range; BCE/year zero are deferred.

Hours are 0–23, minutes and seconds 0–59, nanoseconds 0–999,999,999. Neither `24:00` nor second 60 is accepted. Component accessors expose numbers; composition of an already validated date and time preserves validity.

Month/year addition rejects an invalid target day unless `month_roll::clamp` is explicit. Clamp selects the last valid day of the target month. It is not associative or invertible: clamping January 31 into February loses the original day intent. Arithmetic checks both count overflow and supported calendar range. Weekday and day-of-year queries use the same constexpr calendar core.

`months` and `years` may have checked count arithmetic and an explicit exact 12-month/year conversion, but do not participate in `duration_type`, `duration_cast`, or elapsed-time arithmetic. Duration conversion retains RFC 0008's truncation-toward-zero rule. Calendar epoch decomposition uses floor division; these rules must not be conflated for negative values.

### Instants and clock bridges

`timestamp` stores signed `int64_t` Unix seconds and normalized unsigned nanoseconds. For example, half a second before the epoch is `(-1, 500000000)`. Construction and arithmetic normalize with checked integer operations. Civil conversion can fail when outside years 1–9999 even though the timestamp itself is representable.

This avoids limiting calendar representation to the roughly 1677–2262 range of signed 64-bit nanoseconds. Existing `system_time_point` retains its representation and ABI. Converting it to a timestamp is exact; the reverse conversion is checked. `timestamp::now()` initially wraps the existing system-clock ABI, so its actual clock acquisition range remains that ABI's range. A wider clock ABI is a separate, explicit follow-up if required.

`try_add`/`try_sub` accept fixed durations without first converting the entire value to nanoseconds. `try_elapsed_since` reports overflow if its requested result cannot represent the difference. The initial default difference result can remain nanoseconds; a destination-unit member template permits a wider elapsed range. No wraparound or saturation is implicit.

### Zone ownership, data and discovery

Recommend an installed, pinned IANA bundle as the default data source. `tzdb::load_default()` loads the toolchain's installed resource; `tzdb::load(path)` supports application-controlled updates and reproducible distribution. Both return immutable snapshots, including the IANA release identifier and resource-format version. Missing resources are errors, not silent UTC fallback.

Use a single indexed resource containing TZif bytes and a manifest, rather than treating a lazily read mutable system directory as a snapshot. A loaded database owns immutable bytes. `locate(id)` validates/parses a zone and returns an owning immutable rules handle; repeated lookups may parse again, so clients should retain handles. Hidden mutable caches are not required initially. Explicit clones share ownership. Loading a replacement does not change existing handles or previously computed values.

Zone metadata views borrow from their owning handle. A `zoned_time` retains that handle, so dropping the database is safe. Thread transfer/sharing is permitted only when the concrete source-defined payload satisfies existing capability rules, not by an unchecked assertion that immutable data is safe.

UTC and fixed-offset zones require no database. Offsets have second precision; abbreviations are display labels, not identifiers. Local-zone discovery is a separate fallible `current_zone_id()` service, followed by lookup in an explicit database. Initial implementation targets supported macOS/Linux environments; Windows identifier mapping requires its own verified adapter. Never infer an IANA identity from an abbreviation alone.

The parser implements a documented POSIX-time TZif v2/v3/v4 profile, including future-rule footers. It rejects leap-aware data and unsupported encodings instead of interpreting them as ordinary Unix seconds. Undefined or unsupported coverage returns an error; it must not silently freeze the last observed offset. Follow RFC 9636's boundary rules, checked field sizes and signed offset semantics. Fixed-offset constructors and intermediate arithmetic must also avoid assuming offsets are whole minutes or within a one-hour DST change.

Instant-to-local conversion is unique within supported data/ranges. Local lookup must discover all candidates. The initial public fold form holds two candidates; if a valid but unusual input produces more than two, return `unsupported_rules` rather than discard candidates. Acceptance must validate this profile against the pinned bundle and decide whether a candidate collection is preferable.

For future schedules, applications retain civil intent, zone ID and resolution policy. They may also store the resolved timestamp and database version. Updating rules does not silently reinterpret already stored instants.

### Temporal formatting

Provide default `std::formatting` conformances with deterministic ISO-like representations. Dates use `YYYY-MM-DD`; local readings have no fabricated offset; timestamps use UTC `Z`; zoned values include their actual offset and zone identity. Preserve nonzero fractional seconds and offset seconds. Do not label all such output RFC 3339, which has different offset restrictions.

Proposed custom-pattern API:

- `try_format<T>(T& value, time_pattern<T> pattern) -> expected<string, format_error>`.
- `format<T>(T& value, time_pattern<T> pattern) -> string`, using the existing cleanup-preserving panic convention on failure.
- `try_runtime_format<T>(T& value, string_view pattern)` for configuration/user patterns.
- `try_format_to` for appending to a caller-owned string, with unchanged output on failure.
- A prepared owning runtime-pattern object for repeated formatting without repeated parsing.

Infer `T` from the value, not the pattern. Checked literals use existing implicit consteval construction. Runtime patterns receive equivalent validation with byte-offset errors. Prepared runtime patterns own their text; literal storage must follow existing static-borrow rules.

Initial directives: `%Y`, `%m`, `%d`, `%H`, `%M`, `%S`, `%f` (nine fractional digits), `%I`, `%p` (AM/PM), `%P` (am/pm), English `%a`/`%A` weekday and `%b`/`%B` month names, `%%`, `%:z` (HH:MM offset), `%::z` (HH:MM:SS offset), `%Z` (abbreviation), and `%{zone}` (zone identity). `%:z` rejects an offset with nonzero seconds instead of truncating it. Fixed offsets have a stable numeric identity; UTC has an explicit identity.

A pattern requiring unavailable components is invalid: a date cannot supply hours and a local reading cannot supply a zone. No ambient locale or implicit system zone is consulted. A future explicit locale object may extend this without changing the initial deterministic English contract. Existing `std::format("{}", value)` uses default formatting; `std::format("{:%Y}", value)` is not promised by this RFC.

## Compiler and tooling design

Implement Gregorian math, normalization, mapping policies, TZif parsing and temporal formatting in source library modules. Keep private helpers behind the public `std.chrono` facade. The runtime supplies only narrow existing file/clock services and any necessary OS zone-discovery capability. Do not delegate calendar policy to C++ `std::chrono`, libc global locale state, or compiler special cases.

Before implementation acceptance, compile small probes of checked generic pattern construction, constexpr expected-returning calendar operations, owning payload variants, and shared immutable rules. Where an existing general feature fails, record a focused prerequisite rather than inserting a chrono-only semantic exception.

The frontend owns ordinary constraint/consteval diagnostics and source locations; HIR/MIR retain normal ownership and call semantics; LLVM lowers ordinary source operations. No new syntax, parser tokens or editor grammar are required. LSP hovers/completion should expose source declarations and errors normally. Literal diagnostics should point to the invalid pattern directive when existing immediate-argument location machinery permits it; runtime errors carry byte positions. LLVM is the primary implementation target, with no new C++ parity gate.

Resource installation belongs to packaging/driver infrastructure, with an explicit discoverable default resource path and application override. Installed binaries must be tested outside the compiler checkout.

## Compatibility and migration

This is additive to current chrono and depends on settling RFC 0008/PR #647. Existing nanosecond clocks and casts retain their meanings. `days` adds a fixed unit; `calendar_days`, `months` and `years` cannot silently enter fixed-duration APIs.

No exception-based API is introduced. Error enums distinguish invalid components, overflow, unknown zone, unavailable data, malformed/unsupported data, unsupported coverage, ambiguous/nonexistent local times, and invalid patterns. An umbrella error preserves those causes for applications that combine operations.

Library release, IANA data release and resource-format version are separate. Applications may pin a bundle or choose a newer compatible bundle. Include required data notices and provenance. A release must document which resources distributors must ship.

## Safety and correctness

Private validated representations prevent invalid dates from escaping constructors. All arithmetic and parser size/count operations check overflow. No borrowed view outlives its database/zone/pattern owner. Failed parsing publishes no partial object; failed formatting leaves the destination unchanged through preflight/reservation or rollback.

Treat TZif and bundles as untrusted input. Enforce file-size, count, nesting/record and output limits before allocation; validate offsets and indexes before slicing; reject inconsistent headers and truncated content. Concrete default limits require comparison against the complete pinned database before acceptance. Fuzz parser and mapping code, not only normal zones.

No silent guessing at DST boundaries, data gaps, leap-second semantics or missing resources. Historical/future civil accuracy depends on the supplied data, not just arithmetic correctness. IANA documents historical coverage limits and changes in political rules; expose the data version to make that limitation inspectable.

## Performance and resource costs

Calendar arithmetic is bounded integer work with no required allocations. Named-zone loading and parsing allocate; handle cloning incurs shared-ownership bookkeeping. Retained-zone instant lookup should use binary search over transitions, plus bounded footer-rule computation. Local lookup must be measured separately and must not use an unverified assumption of exactly two offsets to avoid work.

Pattern compilation allocates once for owned runtime text; literal and prepared patterns avoid repeated parsing. Appending into sufficient existing capacity should avoid allocation where practical. All-or-nothing output may need preflight work. Zone snapshots consume memory proportional to bundled bytes plus parsed retained zones; do not claim zero-copy or zero-allocation everywhere.

Measure cold loading, repeated retained-zone lookup, local resolution near transitions, prepared formatting and installed resource size. Record measurements before selecting caches or hard resource budgets. No performance numbers have been measured for this proposal.

## Alternatives and tradeoffs

- **Only durations and Unix integers:** smallest library, but applications repeatedly implement calendar rules, error handling and zone loading.
- **Reuse C++ chrono or platform `localtime`:** can reduce initial code, but transfers semantics and deployment behavior to host implementations. Process-global timezone/locale state also conflicts with explicit independent zone contexts.
- **Model months/years as average durations:** convenient casts but unsuitable for appointments and billing dates. Separate calendar counts make the ambiguity explicit.
- **Allow invalid dates like some C++ calendar values:** useful for intermediate expressions, but every consumer then needs an additional validity check. Validated GTI values simplify safe APIs.
- **Keep only nanosecond timestamps:** fewer types, but unnecessarily limits calendar instant range. A separate split timestamp is additive at the cost of bridges and another name.
- **Use the OS database by default:** smaller packages and automatic system updates, but weaker reproducibility and harder snapshot/discovery guarantees. Explicit system import can be added later.
- **Extend general `format_spec` with raw patterns:** could eventually permit C++-style chrono formatting, but broadens formatter/parser contracts for every type. A dedicated checked API solves the present need without that dependency.

## Unresolved questions

Before acceptance:

1. Confirm pinned default bundle versus OS-data default, resource ownership, installation lookup and independent update workflow.
2. Confirm public civil years 1–9999 and the new split `timestamp` name versus generalizing the existing time-point family.
3. Validate the two-candidate mapping profile against real and adversarial data; choose an extensible candidate collection if rejecting larger folds is undesirable.
4. Compile the specific ownership, constexpr and checked-pattern combinations and record any prerequisite compiler issues.
5. Finalize resource limits, pattern naming (`%{zone}` in particular), and destination-unit elapsed-difference spelling.

Deliberately deferred: leap-second timescales, localization/CLDR, BCE calendars, recurrence engines, general date-string parsing, and additional platform zone-discovery adapters. These are not silently required for the initial accepted scope.

## Implementation plan

No slice below is implemented by this RFC.

1. Settle duration RFC 0008 and PR #647. Add fixed `days`, separate calendar counts, validated date/time types, constexpr Gregorian arithmetic and focused probes.
2. Add split timestamps, checked clock bridges and elapsed operations; retain native ABI compatibility.
3. Add UTC/fixed zones and explicit mapping/result/policy types with ownership checks.
4. Implement bounded TZif reading, future rules, versioned immutable bundles, packaging and installed-resource discovery.
5. Add named-zone conversion, local mapping, resolution policies and supported OS local-zone discovery.
6. Add default format conformances, checked literal/runtime/prepared patterns and transactional append formatting.
7. Add examples and reference pages for every public operation in its module, including elapsed-versus-calendar and DST migration guides. Run implementation validation and release processes only when implementation is authorized.

## Validation and release criteria

- Exhaust a Gregorian 400-year cycle for date/day round trips; check 1900/2000 leap rules, invalid components, range limits and clamp behavior.
- Check negative epoch fractions, signed integer limits, coarse-duration arithmetic without intermediate nanosecond overflow, checked bridges and constexpr/runtime agreement.
- Use pinned fixtures for folds/gaps, exact transition boundaries, 23/25-hour calendar days, non-hour changes, skipped civil dates and historical second-precision offsets. Include UTC/fixed zones without data files.
- Verify footer-based future conversion, coverage failures, malformed/truncated TZif, leap-aware rejection, extreme counts and fuzz input; validate all shipped zone files.
- Test handle survival after database destruction/reload, explicit cloning, borrow rejection and supported thread transfer/sharing. Confirm independent zone operations do not mutate process-global state.
- Compare literal/runtime/prepared formatting, malformed directives and component mismatches, midnight/noon, fractions, offset seconds, English names, runtime byte offsets and unchanged destinations after failure.
- Exercise installed applications on supported macOS/Linux targets, missing resources, explicit bundle overrides, data-version replacement and invalid local-zone discovery.
- Measure cold/warm behavior and allocations before claiming performance. Complete focused compiler/library/runtime/tooling coverage and the implementation repository's release gates. Canonical docs and reference pages must distinguish proposed APIs from shipped APIs until release.

Document validation only checks this proposal's structure; it does not establish compiler, implementation or release readiness.

## Decision record

No design acceptance yet. The owner requested an audit and plan on 2026-11-20. Recommendations and open questions above remain draft decisions. No implementation or release was authorized by this planning request.

## References

- [RFC 0008 proposal](https://github.com/lang-gti-official/rfcs/pull/9): duration units and checked/panicking casts.
- [GTI duration implementation PR #647](https://github.com/lang-gti-official/gti/pull/647): pending duration-family dependency at audit time.
- [Audited chrono source](https://github.com/lang-gti-official/gti/blob/8baa0081bf95afa37b06dec28fffa48c06249774/stdlib/std/chrono.gti): current clock representations and operations.
- [Audited formatting source](https://github.com/lang-gti-official/gti/blob/8baa0081bf95afa37b06dec28fffa48c06249774/stdlib/std/format.gti): format-spec boundary and protocol.
- [Audited memory source](https://github.com/lang-gti-official/gti/blob/8baa0081bf95afa37b06dec28fffa48c06249774/stdlib/std/memory.gti): explicit shared ownership and capabilities.
- [Concepts specification](https://github.com/lang-gti-official/gti/blob/8baa0081bf95afa37b06dec28fffa48c06249774/docs/language/concepts.md): requirements and protocol contracts.
- [Static semantics](https://github.com/lang-gti-official/gti/blob/8baa0081bf95afa37b06dec28fffa48c06249774/docs/language/static-semantics.md): evaluation, ownership and generic constraints.
- [ADR 033](https://github.com/lang-gti-official/gti/blob/8baa0081bf95afa37b06dec28fffa48c06249774/docs/decisions/033-checked-immediate-arguments.md): checked immediate arguments.
- [Standard-library/runtime architecture](https://github.com/lang-gti-official/gti/blob/8baa0081bf95afa37b06dec28fffa48c06249774/docs/architecture/standard-library-and-runtime.md): clock and host-service boundaries.
- [RFC 9636](https://www.rfc-editor.org/rfc/rfc9636.html): TZif interchange and interpretation requirements.
- [IANA theory](https://www.iana.org/time-zones/theory): zone identity, historical limitations and rule complexity.
- [IANA time-zone database](https://www.iana.org/time-zones): data distribution and updates.
- [C++ calendar members](https://eel.is/c++draft/time.cal.ymd.members): alternative validity model.
- [C++ zone exceptions](https://eel.is/c++draft/time.zone.exception): ambiguity/nonexistence as explicit error conditions; GTI uses checked results.
