# RFC 0012: Generated .gtih API views and shared API projection

| Field | Value |
| --- | --- |
| Status | draft |
| Authors | @gti-language-official (with Codex) |
| Created | 2026-11-24 |
| Updated | 2026-11-24 |
| Area | tooling |
| Proposal | https://github.com/lang-gti-official/rfcs/pull/13 |
| Decision | pending |
| Implementation | none |
| Supersedes | none |
| Superseded by | none |

## Summary

Add `gti api`, a project-aware command that generates readable `.gtih` interface listings without executable bodies. The default destination is the project's build directory; `--output-dir <directory>` selects another destination and `--adjacent` places listings beside their `.gti` sources. Listings retain types and the contracts needed to use an API. They are browsing artifacts, never compiler inputs or a second maintained interface.

Investigate and establish a shared, compiler-backed API projection before building separate generation paths. Evolve the existing documentation projection so `.gtih`, the existing documentation-index producer, and future documentation tools consume the same declaration facts. This is a draft design; no command or renderer described here is implemented by this proposal.

## Motivation and goals

A developer opening a large implementation file wants to see its callable interface, types, constraints, documentation and ownership contracts without scrolling through bodies. C++ headers provide this reading surface, but maintaining two declarations and compiling headers are not necessary to provide it. Generated files also work in basic editors, terminal searches and ordinary code review.

The motivating outcome is a project with `src/logger.gti` and several implementation modules. One command produces a compact corresponding listing for each selected source. Another developer can find a method signature, understand its associated types, and navigate to the implementation. An API change produces a comprehensible listing diff.

The architectural outcome is equally important: a documentation generator and an interface generator must not independently rediscover exports, types, constraints, visibility or concept conformances. The shared projection must serve both from one semantic source of truth. A future website can choose its own layout without maintaining another interpretation of GTI.

### Investigation of the existing machinery

Audit baseline: GTI main `ec726745ed6a006f08725898fe0a8767c2e98355` (2026-11-24).

- `DocumentationQueries::standardLibraryIndex` consumes a valid semantic `FrontendResult` with tooling occurrences. It already produces a pointer-free deterministic index, uses `SignaturePrinter`, and retains documentation, source positions and ownership-related traits.
- Its selector is deliberately stdlib-specific: `defaultLibrary`, public access, a standard-library source name, and exclusion of generated/private/internal symbols. Replacing `defaultLibrary` with a package test would not establish module export reachability or a complete user-project API.
- `DocumentationDeclaration` is largely a flat presentation record with an optional signature string. It is not yet a complete structured interface model. Namespace aliases can lack a signature because the exact alias-target presentation fact is absent. This is a concrete information gap to fix at its producer, not a reason for a renderer to guess.
- Conformance operations are intentionally excluded as standalone namespace functions. The shared model needs explicit conformance relationships; publishing synthetic carrier namespaces would be incorrect.
- `gti_docgen` is a build-only stdlib entry point, not a general project documentation command. Its synthetic importing package permits contextual imports such as `std.package`; that synthetic identity must not replace a real project's manifest identity.
- `ProjectFacts` already defines a read-only, shared resolution boundary for documentation/editor consumers. It must be reused for workspace, package, dependency and configuration meaning rather than reparsing manifests in a new tool.

These findings favor generalizing the existing projection and introducing renderer-independent structure where needed. They do not justify a parallel declaration scanner, another type system, or a new persisted compiler IR. See the pinned sources in References.

## Non-goals

- Reintroducing headers, textual inclusion, forward declarations or separate compilation contracts.
- Accepting `.gtih` in an import, as a compilation root, or in package source discovery.
- Round-trip editing, reconstructing implementation bodies, or guaranteeing that a listing is valid executable GTI.
- Implementing a complete documentation website, OpenAPI generator, ABI report or semantic-version compatibility checker.
- Requiring an LLVM/backend change, evaluating extra user code to produce prettier documentation, or making the frozen C++ backend a prerequisite.
- A complete all-configurations API union. A listing describes one explicit resolved analysis configuration.

## Guide-level design

All commands and examples in this section are proposed.

```sh
gti api                         # selected project's normal target selection
gti api --target app            # explicitly select a target
gti api --output-dir api         # location relative to the invocation directory
gti api --adjacent               # src/logger.gti -> src/logger.gtih
gti api --include-private        # include internal declarations for exploration
gti api --check                  # verify existing output without writing
```

Target/profile/platform selection follows the project's existing analysis options; this command must not invent a separate interpretation of those options. Ambiguous target selection is diagnosed. Dependency resolution is read-only: unresolved or unmaterialized dependencies require the existing dependency preparation workflow, not an implicit fetch or lockfile update.

### Destination and file mapping

By default use `<project-build-dir>/api/<target>/<configuration-key>/`, normally under `build/api/`, and mirror package-relative source paths below that root. For example, `src/logger.gti` becomes `build/api/app/<configuration-key>/src/logger.gtih`. The command prints the resolved output root and a summary of generated files.

`--output-dir <directory>` replaces the `build/api` base, retaining target/configuration subdirectories to prevent collisions. An absolute path is accepted. `--adjacent` instead places each listing next to its source. The two location options are mutually exclusive. `--check` works with any location mode. The configuration key is a deterministic identifier for analysis configuration, not a source-content hash: changing source must update the same destination.

Generate one listing per selected package-owned source unit in the resolved target graph. The default public-only mode may produce a notice-only file for a source with no exported declarations; it must not silently switch to internal visibility. A summary explains this and suggests `--include-private` for private application code. Dependencies and the toolchain supply analysis facts but receive no adjacent writes. A dependency can be selected as its own project in a separate invocation.

Sources outside the selected package root require an explicit collision-free ownership mapping; until that is supported, report the unsupported source rather than flatten its path. Adjacent generation requires one target/configuration for any shared source path. An attempt to replace a different configuration's adjacent listing is diagnosed, with build-directory generation suggested. Workspace members can be generated individually; aggregate workspace generation is a future adapter over the same model.

### Contents

Example listing, with the diagnostic enum supplied by a normal module import:

```gti
// Generated GTI API listing; do not edit. Not a compilation input.
// Source: src/logger.gti
export module uptime.logger;
import uptime.errors;
import std.filesystem;

/// Append-only application log.
export class Logger {
public:
  Logger(std::filesystem::path& directory);
  ~Logger();
  expected<void, logger_errc> write(std::string_view message) mut;
};
```

The actual renderer preserves required imports/qualifications and source-facing scopes. It retains class/struct/interface/union shape relevant to the selected visibility, public fields, enum cases and payload shapes, aliases, generic parameters, requirements, concept requirements and conformance signatures. Constructors, destructors, operators and macros are API items too. Bodies of methods, functions and macros are omitted; a concept requirement block is a contract and remains.

Preserve parameter defaults, explicit enum values, declared attributes and constant definitions needed to understand public contracts. Ordinary runtime field/global initializer implementations are omitted with a clear comment. A default or constant expression that contributes to the contract remains an expression; the generator does not recursively inline helper implementations or evaluate new code to replace it with a value. Deleted/defaulted declarations retain their distinguishing markers. An initializer-free field listing must not imply that construction behavior has changed.

The file is GTI-shaped documentation with explicitly documented omission markers. It is not promised to compile. Private state is omitted by default, with a notice where needed to avoid implying a complete layout. Referenced non-exported types are labeled opaque/internal with their resolved identity rather than exposing their private declarations or dropping the reference.

### File overview versus module overview

The initial `.gtih` view is organized by the source that declares an item. Preserve authored export/re-export declarations and links to their origins. Do not copy a dependency's declarations into every re-exporting file or claim one file contains the module's whole API.

The shared projection records effective exports and re-export edges independently of file grouping. A future module overview or docgen renderer can assemble the consumer-visible surface from those relationships. Providing that information in the core is in scope; a separate module-listing CLI mode is not required for the first command.

## Semantic rules

1. **One authority.** Source loading and semantic analysis determine identity, types, accessibility, exports, constraints, ownership and conformance. A renderer formats those facts; it does not infer them by searching text or interpreting serialized signatures.
2. **Visibility.** Default selection is the effective exported API of the selected package/target, including accessible members of exported types and applicable exposed conformances. Public member access alone is insufficient. `--include-private` adds package-owned internal declarations and labels their access/export status; it does not pierce dependency privacy or expose compiler-private helpers.
3. **Contract fidelity.** Preserve reference/lifetime syntax, mutability, consuming receivers, `unsafe` obligations, calling conventions/link attributes where applicable, packs, defaults and requirements. List generic declarations without enumerating monomorphizations. Inferred facts may be displayed as annotations but must be distinguished from written syntax.
4. **Generated declarations.** Record authored, language-generated and compiler-private provenance separately. Language-generated user-visible API must be represented with its origin when the language supplies such a declaration; compiler-private implementation helpers remain hidden. A blanket filter on every generated symbol is not a general export rule.
5. **Configured view.** Output records target, platform, profile and relevant feature/define configuration. Do not merge mutually exclusive configurations into an apparently unconditional interface. Actual package metadata comes from resolved owners. Build-script-derived inputs must already be available or produce a clear preparation diagnostic; this command does not run arbitrary build scripts.
6. **Failures.** CLI generation requires a successful semantic snapshot. Source or projection errors produce normal source-located diagnostics and no new published output set. A missing representable contract is an explicit projection failure, not a fabricated signature or an unreported omission. Existing artifacts remain identifiable as older output.
7. **No compilation effect.** Neither normal builds nor dependency/import discovery consult `.gtih`. Explicit attempts to compile or import it are rejected with a message explaining its documentation role. No declaration in a listing grants access, borrow permissions or ABI guarantees.

## Compiler and tooling design

### Shared projection first, two consumers from the start

Proposed flow:

```text
project facts + source-owner/target context
                    |
          ordinary frontend analysis
                    |
          shared API projection
             /              \
   .gtih text renderer    documentation adapter
                                  |
                         existing JSON schema
                                  |
                         reference website
```

Introduce a general API projection by evolving or extracting the current `DocumentationQueries` implementation. Names such as `ApiProjection` are illustrative, not a commitment to a new subsystem. Keep it in the compiler/tooling library with no dependence on the CLI or website. Both the existing docgen path and the new renderer must use it before the new command is considered complete. A compatibility adapter can retain the existing documentation schema and grouping conventions.

The core carries structured declarations, containment/order, parameter/type/requirement facts, defaults/attributes, conformance relations, effective export edges, documentation and source origins. It can reuse `SignaturePrinter` for canonical text leaves. It must not make renderers reverse-parse a display string to discover parameters, alias targets, type members or export meaning. Add structure only for identified consumers and fidelity requirements; do not mirror the whole AST or semantic database.

| Fact | Producer and owner | Lifetime / invalidation | Consumers |
| --- | --- | --- | --- |
| Package/target/dependency configuration | Existing driver `ProjectFacts` and owner descriptors | Resolved project snapshot; invalidate on relevant configuration/lock/input changes | Frontend setup for CLI, docgen, editors |
| Declaration identity, types, access, exports and conformance | Frontend semantic analysis and source graph | Compiler snapshot; never persist raw IDs or pointers | Shared projection |
| Written defaults, attributes, docs and source origin | Syntax/source occurrences reconciled with semantic declarations | Same source snapshot | Shared projection |
| Structured API records and presentation identities | Shared projection | Owned immutable values; versioned schema at external boundaries | `.gtih`, documentation adapter, future editor view |
| Output locations, file ownership and freshness | Driver publication layer | Generation manifest bound to inputs/configuration/output digests | Command and editor freshness checks |

Snapshot-local pointers and `SymbolId`s must not escape. Use stable project/package-relative source identities and separate declaration identity from presentation grouping and re-export paths. A persisted presentation key need not be a compiler identity. Every externally serialized format needs a version; changing its schema requires explicit consumer migration.

### Required investigation gate

Before implementation commits to the final data model, inventory declaration kinds and contract fields across the existing index, signature printer, source/export graph and semantic occurrence data. Exercise at least one real user package, one re-exporting multi-module package, and the stdlib. Identify which facts already exist, which belong in frontend producers, and which merely require a renderer. Record findings in the eventual implementation plan linked to this RFC.

Resolve the known namespace-alias presentation gap and determine how to expose concept-conformance edges without synthetic namespace leakage. Trace method/field visibility separately from module export reachability. Verify capture of public generic defaults and ownership contracts rather than assuming the current flat signature schema is complete. Confirm project-facts resolution supplies every contextual input; do not create a second manifest resolver.

This investigation may recommend keeping current type names or extracting a small shared layer. The acceptance condition is shared authority and two demonstrated consumers, not the size or naming of a refactor. A `.gtih`-only exporter that leaves duplicated semantic extraction in docgen does not satisfy this proposal.

### Phase and editor boundaries

Selection and projection occur after semantic analysis. Reuse whatever existing compile-time evaluation semantic analysis requires; do not require native code generation or linking merely to render an API. HIR, MIR and LLVM do not become alternate sources of source-facing declarations. No runtime code or ABI changes are proposed.

The renderer owns indentation and omission syntax. Documentation markup is escaped correctly for each output format. Diagnostics use original source spans; a projection failure names the unsupported contract. The existing documentation adapter must preserve its exclusion of conformance operations as namespace functions while the general core retains their actual relationships.

An editor should recognize `.gtih` as a generated listing, offer appropriate highlighting and navigation, and avoid sending it through normal compilation diagnostics. Store generated-range-to-source mappings in sidecar metadata so future go-to-definition can use exact origins, not signature text matching. Rich LSP navigation and an automatically refreshed virtual interface view can follow the initial command; the file remains useful in any plain-text editor. Listings do not inherit source formatter fix-its or writable-code actions.

## Compatibility and migration

This is additive tooling. It does not change `.gti` syntax, import semantics, project build inputs or the reference website's authored content. Default generation stays under the build directory; adjacent writes require `--adjacent`. No automatic generation occurs during ordinary builds.

Prefer ignored generated files for local browsing. Projects may deliberately commit deterministic listings as API snapshots and use `--check` in CI. The command does not edit ignore rules. Existing `gti_docgen` output is preserved through an adapter initially; any necessary schema change is coordinated with the standalone reference repository and explicitly versioned rather than silently rewriting its snapshot.

## Safety and correctness

### Publication and freshness

Stage all rendered outputs before publication. Validate source-to-destination mappings, reject collisions (including case-insensitive collisions on supported filesystems), and never overwrite a `.gti` source. Do not traverse symlinks out of the selected destination or package boundary. An explicitly selected external output directory is allowed; its canonical root is the publication boundary.

A generation manifest tracks schema/tool identity, selected package/target/configuration, rendering options, input-closure fingerprint and output digests. Do not serialize credentials, environment values or absolute checkout paths. Source-relative mappings and content fingerprints permit relocating the same project. Record no wall-clock timestamp in deterministic listings.

Only replace a file tracked as generated by this command and matching its previously recorded output digest, or create a new absent path. A banner alone is not ownership proof. Refuse an untracked or edited existing `.gtih` rather than destroying user work. Adjacent metadata is retained under the project's build API metadata area; if that metadata is missing, refuse to claim ownership of existing adjacent files and explain how to remove or relocate the exact conflicts. Custom output roots carry their own metadata.

Write each file by atomic replacement where supported and publish the generation manifest last. A multi-file or multi-directory update is not promised to be filesystem-atomic: after interruption, manifest/output mismatches make the generation incomplete, and the next invocation diagnoses/reconciles it without accepting a mixed set as current. Remove stale outputs only when tracked, unchanged and inside the owned generation boundary; never recursively clean a user directory. Preserve prior listings on analysis failure.

`--check` resolves/analyzes/renders for comparison but writes nothing, including no directory, output or lockfile creation. Its analysis mode disables cache writes and incidental compiler artifact output; it may read compatible existing caches. It detects missing, extra tracked, stale, edited or incompatible-config output. Proposed exits are 0 for current output, 1 for differences, and 2 for generation/configuration/I/O errors, subject to reconciliation with existing command conventions. Missing materialized inputs are preparation errors. Freshness checks include imported inputs and configuration, not only the adjacent `.gti` timestamp.

### Scope of guarantees

The listing is a view of one configuration, not a proof of ABI stability, complete behavior, security or semantic-version compatibility. Hidden layout is not exposed by implication. Visibility filtering is enforced before serialization, and both renderers are tested for compiler-private leakage. Syntax appearing in defaults or comments must never be interpreted as an output path or executed by the renderer.

## Performance and resource costs

There is no program runtime or generated machine-code cost. Generation pays for project resolution, the semantic work needed for the selected graph, projection and rendering. Reuse existing compiler caches only with their normal invalidation guarantees. Analyze a shared unit once per compatible configuration rather than once per output file or format. Do not mandate retaining a second full semantic graph.

Measure cold/warm generation time, peak memory, index/listing size and unchanged-write behavior on a small package, a multi-module re-exporting package, a generic-heavy package and the stdlib. Compare current docgen with the shared projection plus its compatibility adapter; investigate regressions in semantic work, memory retention and output size. Measure combined rendering from one projection against separate invocations. No measurements exist for this proposal.

## Alternatives and tradeoffs

- **Only generated HTML documentation:** preserves one declaration source but does not provide a compact editor/terminal file. Both formats should share extraction.
- **Strip bodies with a text/parser script:** simpler initially, but cannot reliably represent configured exports, semantic ownership, aliases, conformances and generated provenance. It creates the duplicated maintenance problem this proposal aims to avoid.
- **Render `.gtih` directly from today's documentation JSON:** a useful prototype, but insufficient as the final design because the current selector and flat optional signatures omit required general-project facts. Extend the common projection rather than reverse-parsing JSON signatures.
- **A separate API scanner alongside docgen:** independently evolves visibility and signature policy and risks contradictory views. Rejected as the planned implementation architecture.
- **Editor-only virtual views:** avoid stale files but exclude simple editors, terminal searches and committed snapshots. Preserve this future consumer through the same model.
- **Manually maintained `.gtih` files used by compilation:** creates synchronization and language semantics the user did not request. Generated browsing artifacts provide the benefit without that obligation.
- **Adjacent output by default:** convenient navigation, but clutters source directories and collides across configurations. Build-directory output is the default; adjacent output remains explicit.

## Unresolved questions

1. What is the smallest structured extension to the existing documentation model that faithfully represents all supported declaration kinds, exports and conformances? Resolve through the investigation gate before committing the implementation architecture.
2. Which exact configuration-key spelling and shared driver publication utilities should the command use? Preserve collision freedom, stable paths across source edits and human-readable command output.
3. Which omission markers best distinguish hidden fields and omitted initializers while keeping normal editor highlighting useful? Define a versioned listing convention and test it before release.
4. Can the existing JSON schema remain unchanged through the adapter for all current consumers, or do corrected aliases/relationships warrant a coordinated schema revision? New core facts need not all be exposed in the legacy adapter.
5. What is the minimum editor integration required at launch to prevent misleading compiler diagnostics for `.gtih`? Rich navigation is a follow-up, but source-file classification must be correct from the start.

The output defaults, optional explicit directory and adjacent mode, retention of types/contracts, non-compilation role, and shared-authority requirement are proposed core rules. The questions above do not authorize shipping two parallel extractors.

## Implementation plan

1. **Inventory and model proof:** audit the pinned machinery against current main, build the declaration/contract coverage matrix, and resolve known alias/export/conformance gaps at the proper producer. Record evidence and final model choice in an implementation plan after design acceptance.
2. **Shared core and existing consumer:** generalize projection selection and structured data, then move existing docgen through a compatibility adapter. Prove existing index output parity except for separately explained corrections; retain all current tests.
3. **Interface renderer:** render package-owned `.gtih` records from the same projection. Add snapshots covering all supported declaration families and cross-renderer fact comparisons. Do not implement a second source traversal in the renderer.
4. **Project command and publication:** reuse `ProjectFacts`, add target/configuration selection, default/custom/adjacent paths, tracked publication, source maps and `--check`. Exercise real project and dependency contexts.
5. **Tooling and documentation:** recognize the generated extension, document limitations and workflows, and coordinate any documentation schema migration with the reference repository. Add richer navigation later without another projection.

This RFC does not authorize implementation. Subsequent implementation tracking must link back to the accepted design and apply GTI's normal focused validation and merge-queue lifecycle.

## Validation and release criteria

- Golden listings cover namespaces/aliases, classes/structs/interfaces/unions, enum values/payloads, fields, functions, methods, constructors/destructors, operators, macros, generics/packs, constraints, defaults, declared attributes, explicit lifetime/borrow contracts, mutating/consuming/unsafe signatures, concepts and conformances. Preserve contracts and remove executable bodies.
- Test an unrelated user package, multi-file modules, explicit exports/re-exports, same-named overloads and private helper types. Verify public-only versus internal views, ownership of imported declarations, contextual `std.package`, and target-dependent APIs.
- Assert `.gtih` never enters source discovery/import/compilation, and adding or editing a listing cannot change normal build meaning. Diagnose explicit misuse.
- Compare shared declaration facts through both renderers and preserve the existing documentation-index regression suite. Add a new API field once in the core and demonstrate both consumers use it; no duplicate semantic extraction is accepted.
- Verify deterministic output across repeated runs and relocated checkouts, no absolute paths/timestamps, and unchanged artifact timestamps when bytes are unchanged. Configuration changes, imported source changes and tool/schema changes invalidate freshness appropriately.
- Exercise default/custom/adjacent destinations, spaces, symlinks, case collisions, sources outside package roots, multiple targets, edited/untracked files, stale cleanup, interrupted publication and missing manifests. `--check` must leave the filesystem unchanged.
- Assert failures do not publish a new apparently complete generation, source maps resolve to exact declarations, generated helpers do not leak, and no renderer guesses a missing semantic fact.
- Measure the workloads described above. Validate path/publication and editor behavior on supported macOS and Linux hosts. Compiler implementation follows its focused-check policy; complete integration validation belongs to CI. No compiler build is required merely to validate this RFC text.
- Update canonical compiler/tooling and CLI documentation on implementation, including the generated-format convention, configuration scope and documentation adapter. A document check passing does not establish implementation or release readiness.

## Decision record

2026-11-24 — The owner requested an RFC for generated `.gtih` API listings, with build-directory output by default, an explicit output location option and adjacent generation. The owner also requested investigation of a shared foundation for API generation and docgen to avoid duplicate maintenance. This draft proposes that shared projection as the first implementation prerequisite. Design acceptance and implementation remain pending.

## References

- [Existing documentation model](https://github.com/lang-gti-official/gti/blob/ec726745ed6a006f08725898fe0a8767c2e98355/include/gti/documentation.h): current deterministic presentation records and stdlib-only query boundary.
- [Existing projection implementation](https://github.com/lang-gti-official/gti/blob/ec726745ed6a006f08725898fe0a8767c2e98355/src/compiler/documentation.cpp): semantic selection, `SignaturePrinter`, alias limitations and conformance filtering.
- [Docgen entry point](https://github.com/lang-gti-official/gti/blob/ec726745ed6a006f08725898fe0a8767c2e98355/src/docgen/main.cpp) and [synthetic consumer](https://github.com/lang-gti-official/gti/blob/ec726745ed6a006f08725898fe0a8767c2e98355/src/docgen/frontend.h): current build-only consumer and explicit package context.
- [Read-only project facts](https://github.com/lang-gti-official/gti/blob/ec726745ed6a006f08725898fe0a8767c2e98355/include/gti/driver/project_facts.h): shared project meaning for documentation, editor and analysis clients; avoids another manifest resolver.
- [Reference-documentation architecture](https://github.com/lang-gti-official/gti/blob/ec726745ed6a006f08725898fe0a8767c2e98355/docs/architecture/reference-documentation.md) and [projection tests](https://github.com/lang-gti-official/gti/blob/ec726745ed6a006f08725898fe0a8767c2e98355/tests/documentation_index_tests.cpp): current consumer contract and evidence to preserve.
- [GTI phase architecture](https://github.com/lang-gti-official/gti/blob/ec726745ed6a006f08725898fe0a8767c2e98355/docs/architecture/overview.md): source/semantic authority and tooling boundaries.
- [Rustdoc](https://doc.rust-lang.org/rustdoc/index.html) and [cargo-public-api](https://github.com/cargo-public-api/cargo-public-api): precedents for generated interface browsing and textual API projections; neither specifies GTI semantics.
