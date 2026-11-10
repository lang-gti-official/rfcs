# RFC 0005: Versioned symbol mangling for GTI

| Field | Value |
| --- | --- |
| Status | draft |
| Authors | @gti-language-official (with Claude Code) |
| Created | 2026-11-10 |
| Updated | 2026-11-10 |
| Area | compiler |
| Proposal | pending |
| Decision | pending |
| Implementation | none |
| Supersedes | none |
| Superseded by | none |

## Summary

Define one versioned, reversible, compiler-independent encoding ("mangling") for
every compiler-owned GTI symbol that appears in an object file's symbol table,
before compiled GTI libraries ([ADR 032]) widen beyond their current bounded
scalar profile. A mangled name encodes the declaration's semantic identity
(logical owner, qualified path, overload parameters and concrete generic
substitution) so that tools can recover a readable GTI path from the symbol
alone. Contract integrity (borrow contract, result recipe, optimization policy)
is checked separately, rather than being the name. The scheme ships with a
demangler.

This is a draft. Nothing here is implemented. Today, exported library symbols
are an opaque SHA-256 digest, and private symbols are numbered.

## Motivation and goals

### Current behavior (verified against `main`, 2026-11-10)

- **Exported library callables.** `compiledScalarSymbol`
  (`src/compiler/compiled_scalar_unit.cpp`) builds
  `__gtilib_callable_v4_<64 hex>`. The 64 hex digits are the SHA-256 of a
  `gti.callable.4:` contract string that concatenates:
  - the persistent function key;
  - the result recipe;
  - the type metadata;
  - the borrow origin, parameter and access;
  - the inlining and cold attributes.

  The persistent key (`include/gti/persistent_declaration.h`) is already a
  structured identity: the owner (package, target, module and optional unit),
  the qualified name, a source-local flag, and the parameter types.
- **Private compiler-generated symbols** are internal-linkage names built from
  numeric MIR/HIR identities. Examples: `__gti_native_v1_body_<kind>_<owner>`,
  `__gti_native_v1_g<N>`, `__gti_native_v1_enumerator<N>` and
  `__gti_native_v1_thread_<id>_entry` (`src/compiler/llvm/body.cpp`,
  `places.cpp`, `threads.cpp`).
- **Debug information** deliberately omits DWARF linkage names, so that
  debuggers show the GTI qualified name rather than the opaque symbol
  (`src/compiler/llvm/debug_info.cpp`).
- **Names outside this RFC's scope** are kept exactly as they are:
  - runtime services, spelled `gti_rt_*_v1`;
  - `extern "C"` declarations, `[[link_name("...")]]` and embedding exports,
    which keep exact C spellings
    ([programs-and-targets](https://github.com/lang-gti-official/gti/blob/main/docs/language/programs-and-targets.md)).

### The problem

The `__gtilib_callable_v4_` digest repeats the main defects of Rust's legacy
mangling, which Rust took from 2018 (RFC 2603) to late 2025 to move away from
([Rust blog, 2025-11-20][rust-v0]):

1. **Not reversible.** A profiler, crash report, `nm` listing or linker error
   shows 64 hex digits. No tool can recover `geometry::area(Rect)` from the
   symbol.
2. **Identity and integrity are fused.** Changing an inlining hint or a borrow
   contract changes the symbol, by design: ADR 032 uses that change to reject a
   stale object. But it also means the name cannot double as a stable identity
   for tooling, and every new contract field bumps the profile version (`v4`
   today).
3. **No reserved shape for generics.** ADR 032 requires that "external symbol
   keys must derive from artifact logical identity, declaration key and
   concrete substitution, with a versioned encoding". The current profile has
   no encoding for a substitution, and its private scheme uses numeric IDs that
   ADR 032 forbids persisting.
4. **Length.** Every exported callable costs at least 85 bytes in the string
   table, even `main::f()`.

Rust's experience shows the expensive part: debuggers, profilers and
demanglers learned the legacy format, and moving them took years. GTI has no
external tooling that depends on any symbol format. The bounded library profile
already documents that it promises no cross-version ABI stability, and older
development metadata already requires rebuilding. Fixing the format now is
therefore close to free. Fixing it after general libraries ship is not.

### Goals

- Encode the semantic identity already defined by the persistent key, plus
  concrete generic substitutions, reversibly.
- Use symbol characters from `[A-Za-z0-9_]` only (Rust's legacy `.` broke some
  platforms), plus a unique, versioned prefix that tells GTI symbols apart from
  C, Itanium C++ (`_Z`) and Rust (`_R`).
- Keep the encoding independent of compiler internals: no numeric MIR/HIR IDs,
  pointer orders or hash tables. Two compilers that agree on GTI semantics
  produce the same name.
- Provide a demangler as a supported `gti` tool before the first general
  library release.
- Keep names compact through back-references (substitutions) for repeated
  paths and types.

Success means a symbol from any GTI object demangles to its GTI path and
substitution, and stale or incompatible objects are still rejected exactly as
they are today.

## Non-goals

- **A stable ordinary GTI ABI across compiler versions.** ADR 032's
  exact-toolchain reuse rule is unchanged. A stable name for a declaration
  does not make its calling convention or layout stable.
- **Changing C, embedding or runtime spellings.** `extern "C"`, `link_name`,
  embedding exports and `gti_rt_*` keep their current rules.
- **Inventing GTI identity in the backend.** [ADR 024] rejects "backend name
  mangling that invents different GTI types". Mangling encodes an identity that
  semantics and HIR have already decided. It never disambiguates two
  declarations that GTI considers the same, or separates two that it considers
  different.
- **Linker selection.** GTI links through the selected native compiler with the
  platform linker. Adopting lld is a separate decision.
- **C++ backend support.** The C++ backend is frozen and separate from default
  builds and CI, and it is not an acceptance gate.

## Guide-level design

Users rarely see mangled names. The visible changes:

```text
# today
$ nm -g libgeometry/unit.o
0000000000000000 T ___gtilib_callable_v4_9c1f…(64 hex)
$ gti demangle ___gtilib_callable_v4_9c1f…
error: not a reversible GTI symbol

# proposed (illustrative spelling; the grammar is unresolved)
$ nm -g libgeometry/unit.o
0000000000000000 T __G1N8geometry4areaE…
$ gti demangle __G1N8geometry4areaE…
geometry::area(geometry::Rect) -> f64   [package geometry, target lib]
$ nm -g libgeometry/unit.o | gti demangle   # filter mode, like c++filt
```

A linker error for a missing dependency names the GTI declaration once the
output is passed through `gti demangle`. Profilers that do not know the scheme
show the mangled form, which now contains the readable path components (as
Itanium and v0 do).

Failure cases:
- If an object's symbol has the right mangled identity but a different
  contract fingerprint, import rejects it with a contract-mismatch diagnostic,
  not a linker error.
- An unknown scheme version demangles to an explicit "unsupported GTI mangling
  version N" message.

## Semantic rules

The mangled name is a function of the following, and only these:

1. **Scheme version.** It is part of the prefix, so a future scheme can coexist
   and be detected.
2. **Logical owner.** The package, target and module from
   `PersistentDeclarationOwner`, plus the logical source-unit key for
   source-local (`static`) declarations. It never contains a checkout path or a
   source digest.
3. **Declaration path.** The namespace and class components and the declaration
   name. Special members (constructor, destructor, field initializers, thread
   entry) get reserved tags rather than spellable identifiers.
4. **Overload identity.** The parameter types, using the same rule as the
   persistent key: return types and bodies do not participate.
5. **Concrete substitution.** The type arguments and compile-time value
   arguments of a generic instance, as recorded by HIR. Value arguments use a
   canonical encoding: integers in decimal with a sign, and other constant
   kinds are unresolved (see below).
6. **Disambiguator, where semantics needs one.** Closures and lambdas, and
   multiple instances of the same anonymous construct, get an index taken from
   a source-order rule defined by semantics. It never comes from a MIR
   numbering.

The name excludes:
- the borrow contract;
- the result recipe;
- optimization or inlining policy;
- the target triple;
- the compiler version.

Those values are carried in a **contract fingerprint**, which import checks
before admitting an object. This RFC proposes keeping the fingerprint in the
bundle's interface metadata, keyed by the mangled name, rather than as a
symbol suffix. That way a stale object with a matching name is rejected at
import with a GTI diagnostic. An object linked without import (a hand-built
link line) is not protected. Whether that is acceptable, or whether a short
fingerprint suffix should be kept as a linker-level backstop, is an open
question.

Two declarations that semantics treats as distinct must mangle differently.
That includes the same qualified name in different packages, and different
substitutions. A collision is a compiler bug, detected by the verifier
described under Safety and correctness.

## Compiler and tooling design

- **Authority.** Semantics and HIR own identity. A new
  `MangledIdentity`-style value is computed from HIR instances and the
  persistent registry. It is not computed by LLVM: LLVM consumes a name from
  the linkage plan, as ADR 032 already requires.
- **Library export and import.**
  - `CompiledScalarUnitBuilder` and the importer replace `compiledScalarSymbol`
    with the mangled identity plus a metadata fingerprint check.
  - The envelope and profile versions change, and old bundles require
    rebuilding, which is consistent with existing practice.
- **Private symbols.**
  - The first slice may keep the numbered `__gti_native_v1_*` names, since
    they are internal and never persisted.
  - A later slice gives them readable local mangled names (with an
    internal-only tag) so that perf and Instruments symbolication is readable
    in unstripped binaries.
  - Doing this requires deterministic disambiguators for compiler-generated
    helpers that have no source identity.
- **Demangler.** `gti demangle` (argument and stdin filter modes) and a small C
  library entry, so that LLDB or perf integrations can use it later. It lives
  next to the encoder and shares its grammar tables, and both are tested
  against one corpus.
- **Debug information.** Keep omitting linkage names for now. Once the
  demangler exists, decide whether exported functions should carry
  `DW_AT_linkage_name`. Debuggers without a GTI plugin would then show the
  mangled form, which is the reason it is omitted today.
- **Diagnostics.** The driver's object-validation and link-failure messages
  demangle the symbols they report.
- **LSP and formatter.** Not affected.

## Compatibility and migration

- **Library bundles.** `.gtilib` bundles built with `__gtilib_callable_v4_`
  stop being importable. They are already development-only, with exact
  toolchain matching, so a rebuild is the migration. The change needs a
  `Release-Impact` breaking entry in the implementation PR.
- **Version detection.** The scheme version in the prefix lets the importer and
  demangler identify an unsupported scheme explicitly.
- **Earlier decisions.** ADR 032's "versioned encoding" requirement is
  satisfied rather than revised. ADR 024's rule against backend-invented
  identity is preserved.
- **Opt-out.** None proposed. Unlike Rust, there is no installed tool ecosystem
  to protect, and a dual scheme would double the test surface.

## Safety and correctness

- **Injectivity.** A verifier, run under the compiler's validation mode
  (`GTI_COMPILER_VALIDATION`, in line with proportionate self-checks), asserts
  that distinct HIR identities in one link unit produce distinct mangled names.
  It also checks that every name demangles back to the identity that produced
  it.
- **Round trip.** Every corpus symbol must satisfy `demangle(mangle(x)) == x`.
  Malformed-input tests for the demangler cover truncation, bad lengths, bad
  back-references and deep nesting, each with explicit size and depth limits.
- **Bounded decoding.** The demangler bounds recursion depth, back-reference
  count and output size. It never allocates in proportion to a length field it
  has not validated.
- **Stale objects.** The existing rejection of stale objects is preserved
  through the fingerprint check. A negative test imports an object whose
  identity matches but whose borrow contract differs, and requires rejection.
- **Reserved prefix.** The prefix begins with an underscore and an uppercase
  letter, so GTI source identifiers and C spellings cannot produce it.
  `extern "C"` and `link_name` spellings that begin with it are rejected, so a
  user cannot forge a GTI symbol.

## Performance and resource costs

Estimates only; nothing has been measured.

- **Symbol size.** Short generic-free names should be shorter than the current
  85-byte digest. Deeply generic instances could be longer, and
  back-references bound the growth.
- **Link time.** String table size affects Apple ld and GNU ld more than lld;
  the article notes lld softens v0's cost. Acceptance needs a comparison of
  string table bytes and link time on a library-heavy example against the
  `v4` digest.
- **Compile time.** Mangling is linear in identity size and replaces a SHA-256
  over a larger contract string, so no regression is expected. Measure it with
  `scripts/compile_time_compare.py`.
- **Runtime.** No effect: symbol names do not change generated code.

## Alternatives and tradeoffs

1. **Keep the SHA-256 digest.**
   - For: simple, already implemented, and the fused integrity check costs
     nothing at link time.
   - Against: it is not reversible, has no generic encoding, and every
     contract change bumps the version. This is the option Rust spent years
     escaping.
2. **Adopt Itanium C++ mangling (`_Z`).** Existing demanglers would show
   something. But it would misrepresent GTI semantics as C++ (forbidden by the
   targets specification), cannot express GTI owners or compile-time values,
   and invites collisions with real C++ symbols.
3. **Adopt Rust v0 (`_R`) unchanged.** It is well designed, but it claims to
   be Rust: tools would label GTI symbols as Rust and its crate model does not
   match GTI owners. Borrowing its structure (base-62 numbers, back-references,
   punycode identifiers) under a GTI prefix gets the benefit without the
   misrepresentation.
4. **A readable name plus a hash suffix** (Rust legacy style). This is
   partially reversible and keeps the integrity check in the name, but it is
   still fused and it adds length.
5. **Delay until general libraries.** Cheaper now; more expensive once bundles,
   profiles and tooling exist.

The tradeoff the owner accepts: a new grammar plus a demangler to maintain, and
a rebuild of development bundles, in exchange for reversible names and a
generic-ready identity before compiled libraries widen.

## Unresolved questions

1. **Prefix and grammar spelling.**
   - The `_G` / `__G` family is the working assumption. That nothing else
     claims it needs checking.
   - Mach-O adds a leading underscore and ELF does not, so the scheme has to
     say which form is canonical.
   - The final grammar should borrow v0's structure.
2. **Identifier encoding.** Whether GTI identifiers can contain non-ASCII
   characters now or later, which decides whether punycode (as in v0) is
   needed.
3. **Compile-time value arguments.** Canonical encoding for non-integer
   constant kinds (floating point, text, aggregates), following the
   constant-evaluation direction (`L-CONST-01`).
4. **Fingerprint placement.** Metadata only, or also a short symbol suffix as a
   linker-level backstop for links that bypass import.
5. **Private symbols.** Whether readable local names are in the first scope or
   a later slice, and the determinism rule for compiler-generated helpers with
   no source identity.
6. **Debug linkage names.** Whether to emit `DW_AT_linkage_name` for exported
   symbols, and whether to ship an LLDB formatter or plugin.
7. **Disambiguators.** The exact semantic source-order rule for lambdas and
   closures, and whether it survives edits elsewhere in a file (which matters
   for incremental reuse).

## Implementation plan

Not scheduled. Implementation would follow acceptance and the GTI
implementation queue (`docs/plans/implementation-sequence.md`), after the
current RFC 0004 window.

1. **Grammar and demangler.** The specification text in the GTI repository's
   build and driver architecture document, the encoder and decoder library,
   `gti demangle`, and a round-trip and malformed-input corpus. No compiler
   output changes.
2. **Exported callables.**
   - Replace `compiledScalarSymbol` with the mangled identity plus a metadata
     fingerprint.
   - Bump the bundle and profile versions.
   - Make the driver's object validation and link diagnostics demangle the
     symbols they report.
3. **Generic substitutions.** Encode concrete substitutions when compiled
   libraries admit generic instances. This slice ships with that ADR 032
   milestone, not before.
4. **Private symbols (optional).** Readable local names and deterministic
   helper disambiguators.
5. **Tooling follow-ups.** The debug linkage-name decision, and LLDB or perf
   integrations.

## Validation and release criteria

- **Round-trip and injectivity.** Tests over HIR identities from the example
  corpus and the compiled-library tests. The injectivity check stays enabled
  in validation builds.
- **Negative cases:**
  - an identity match with a contract mismatch is rejected;
  - an unknown scheme version is reported explicitly;
  - forged `extern "C"` spellings with the reserved prefix are rejected;
  - malformed-input demangler cases stay within explicit memory and depth
    limits.
- **Platforms.** Both Mach-O and ELF, including leading-underscore handling,
  checked with `nm` output from real objects on macOS arm64 and Linux x64.
- **Existing coverage.** The compiled-library CTest entries
  (`compiled_primitive_library`, `compiled_dependency_project`,
  `compiled_borrow_contract`, `compiled_scalar_library_cost`) pass with the new
  names.
- **Performance.** String table size and link time compared against `v4`, and
  compile-time comparison with no regression.
- **Documentation.** The canonical specification and architecture documents
  are updated in the implementation PRs.

## Decision record

No design decision yet.

## References

- [ADR 032][ADR 032]: compiled library bundles. It sets the requirement for a
  versioned encoding derived from logical identity and concrete substitution,
  and documents the current `v4` SHA-256 symbols.
- [ADR 024][ADR 024]: source module interfaces. It rejects backend mangling
  that invents GTI identity.
- [programs-and-targets](https://github.com/lang-gti-official/gti/blob/main/docs/language/programs-and-targets.md):
  C++ mangling and private compiler identifiers are not GTI semantics, and
  `extern "C"` symbols are not mangled.
- `src/compiler/compiled_scalar_unit.cpp` and
  `include/gti/persistent_declaration.h`: the current symbol construction and
  persistent identity.
- [Rust blog: switching to v0 mangling on nightly (2025-11-20)][rust-v0]:
  legacy defects (no generic arguments, internal hash, `.` characters, hard to
  tell apart from C++) and the years-long tooling migration.
- [Rust RFC 2603](https://rust-lang.github.io/rfcs/2603-rust-symbol-name-mangling-v0.html):
  the v0 grammar, a source of structure (base-62, back-references, punycode).
- [Itanium C++ ABI mangling](https://itanium-cxx-abi.github.io/cxx-abi/abi.html#mangling):
  the dominant native scheme, considered and not adopted.

[ADR 032]: https://github.com/lang-gti-official/gti/blob/main/docs/decisions/032-compiled-library-bundles.md
[ADR 024]: https://github.com/lang-gti-official/gti/blob/main/docs/decisions/024-source-module-interfaces.md
[rust-v0]: https://blog.rust-lang.org/2025/11/20/switching-to-v0-mangling-on-nightly/
