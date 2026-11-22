# RFC 0010: Composable input, output and file streams

| Field | Value |
| --- | --- |
| Status | draft |
| Authors | Codex |
| Created | 2026-11-22 |
| Updated | 2026-11-22 |
| Area | stdlib |
| Proposal | https://github.com/lang-gti-official/rfcs/pull/11 |
| Decision | pending |
| Implementation | https://github.com/lang-gti-official/gti/pull/667 |
| Supersedes | none |
| Superseded by | none |

## Summary

Provide input, output and bidirectional stream operations over the byte I/O protocols, with owning file streams that either open in the constructor or return a recoverable result from a static factory. Permit mutable, receiver-borrowing shift operators for insertion and extraction.

## Motivation and goals

A program should be able to parse its real input from a file and feed memory into the same parser in tests. A log writer should be able to open a path, detect an open failure, format records, and report a final flush or close failure. A random-access program should be able to read a record and write its replacement at the logical stream position. GTI already provides byte transfers, file handles, buffering, generic readers and writers, and line reading.

## Non-goals

This proposal does not change the representation of built-in integers, native file descriptors, or the existing byte reader and writer APIs. C++ locale facets, native exceptions and its ABI are distinct facilities. Do not introduce a private language rule for a named library stream.

## Guide-level design

```gti
import std.fstream;
expected<void, std::io_errc> log_value(std::string_view path, int value) {
  mut auto out = ?std::ofstream::open(path);
  out << value << '\n';
  if (!out) { return unexpected(out.error()); }
  out.close();
  if (!out) { return unexpected(out.error()); }
  return;
}
```

The convenience spelling is `mut std::ifstream in{path};`. Opening occurs during construction. The object remains inspectable on failure. The factory performs one open and returns the same failure code through `expected`. To open a file on an existing stream, call its mutable `try_open` method:

```gti
mut std::ifstream in{};
?in.try_open(path);
```

A failed `try_open` sets the stream’s failure state and returns its error. Opening a stream that already owns a file reports failure and preserves the original handle. A successful open clears the stream state, including failure from a previous attempt. `is_open()` reports whether the stream owns a file handle.

## Semantic rules

Input, output, and combined streams share reusable state and operations. The public surface should use the familiar spellings for formatted insertion and extraction, unformatted get/peek/read/ignore/putback/unget and output put/write/flush, last unformatted input count, positioning, and state observation and reset. Distinguish EOF, format failure and transport failure. Specify partial progress, delimiters, token boundaries, and numeric overflow; check every overload using a real caller. Map file and memory operations onto this common implementation.

File streams expose default and path construction, a static `open` factory, a mutable `try_open` returning `expected<void, io_errc>`, `is_open`, `error`, `close` and access to the associated buffer, with familiar modes and supported positioning. A bidirectional file buffer maintains one logical cursor. Reconcile unread input on transition to writing, flush pending output before entering reading, and synchronize position for seeking. A close or flush that callers need to observe is explicit. Destruction releases the resource once.

A shift overload may use a mutable receiver and return a mutable reference of its receiver type. This shape must respect the method receiver's borrowing contract. A chain must neither copy the owner nor extend its lifetime, and may not confer mutable access to an immutable value. The RHS of extraction can be a second mutable reference, subject to normal overlap rules. Existing owned-result and built-in shifts keep their semantics.

## Compiler and tooling design

Use the existing operator tokens, declaration syntax and overload resolution. Record the selected method and returned place like an ordinary checked call. HIR and MIR must retain the receiver's dependency, argument borrows and lifetimes through chained calls. LLVM executes the same checked calls. Editor diagnostics and formatting use ordinary compiler facts. Source-defined stream adapters own policy; the runtime supplies only host file operations. Reuse existing numeric conversion and formatting facilities where their contracts match stream behavior.

## Compatibility and migration

Existing std.cstdio and std.io users continue to work. Expose discoverable modules for ios, istream, ostream and fstream. Users can adopt the file wrappers independently of their file format and keep ordinary expected propagation. Use recognizable C++ names, and document the GTI contract for file creation, state, and explicit errors.

## Safety and correctness

A returned shift reference is bounded by the original receiver. Reject escapes, overlapping accesses and immutable receivers even through a chain. A generic parser must respect the borrowed lifetime of its buffer. A moved file transfers ownership exactly once. Input and output views of a single fstream observe the same state and logical position. File handles and temporary read-ahead views must not outlive their owner. No work may proceed around a compiler ICE; reduce it and fix its owning phase before resuming the feature.

## Performance and resource costs

Shifts should cost an ordinary method call and introduce no allocation or stream copy. Buffering should amortize host calls across small reads/writes. Exercise large-file sequential reads, alternating reads and writes, and repeated formatted insertion; inspect optimized output for object copying or allocations per operation. There are no benchmark results yet.

## Alternatives and tradeoffs

A static factory alone makes failures explicit but loses familiar construction. A constructor alone requires manual failure propagation. Offering both adds little when they share the same opening primitive. Independent file reader and writer cursors are inadequate when read-ahead and buffered output operate on the same descriptor. Requiring a C++ virtual-inheritance graph would impose an object model on clients that already compose through GTI reader/writer contracts.

## Unresolved questions

Validate the concrete mapping of each C++ member to GTI ownership and error handling, especially replacement of buffers, runtime-polymorphic streams, swaps and close failure. Any fundamental language prerequisite beyond checked mutable shifts goes back to the owner before work continues. Track gaps explicitly during API review.

## Implementation plan

1. Establish and execute the checked mutable-shift contract on user-defined types, including rejection tests.
2. Implement shared stream state and input/output methods against reusable buffer contracts. Exercise both memory and file transports.
3. Implement file ownership, open modes, cursor reconciliation, and the three file facades. Combine with the common layer and exercise path construction, static factory opening, and opening an existing stream.
4. Validate interoperability, document the method map and failure semantics, measure representative operations and integrate through the compiler repository.

## Validation and release criteria

Exercise chained I/O, mixed-type formatting, extraction failure, clean EOF, partial transfers, buffering and open/close failures. Use existing and missing temp paths, test truncation and appending, and check the resulting bytes after switching direction and seeking. Check move/destruction, equivalence of opening through the constructor, factory and existing stream, preserved existing shifts, and borrow-checker rejections. Run source tests on LLVM with an optimized compiler, affected editor/semantic consumers, native smoke and normal CI. RFC document checks establish only the document's consistency.

## Decision record

The owner requested both opening forms, observable errors and familiar stream methods, and on 2026-11-22 explicitly authorized checked mutable shift overloads in the implementation chat. On the same day the owner selected static `open` for the factory and instance `try_open` for an existing stream. Both spellings work with ordinary GTI member lookup. The overall proposal remains a draft.

## References

- [GTI composable byte I/O](https://github.com/lang-gti-official/gti/blob/main/docs/language/io.md#composable-buffered-io) specifies the underlying contracts.
- [GTI grammar](https://github.com/lang-gti-official/gti/blob/main/docs/language/grammar.ebnf) records the existing operator rules.
- [C++ input streams](https://eel.is/c++draft/istream), [output streams](https://eel.is/c++draft/ostream) and [file streams](https://eel.is/c++draft/file.streams) define the comparison surface.
