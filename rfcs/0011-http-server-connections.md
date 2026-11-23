# RFC 0011: HTTP/1.1 server connections for third-party servers

| Field | Value |
| --- | --- |
| Status | draft |
| Authors | @gti-language-official (with Codex) |
| Created | 2026-11-23 |
| Updated | 2026-11-23 |
| Area | stdlib |
| Proposal | https://github.com/lang-gti-official/rfcs/pull/12 |
| Decision | pending |
| Implementation | none |
| Supersedes | none |
| Superseded by | none |

## Summary

Add a synchronous HTTP/1.1 protocol API to `std.http` for one already-connected duplex byte stream. A GTI package can accept a TCP stream, wrap it, read a request head, stream or decline the body, and send an ordered response. The package decides when to do each operation. No standard HTTP listener, accept loop, handler type, router, or executor is required.

## Motivation and goals

Consider an uptime monitor. Its background scheduler uses the existing HTTP client to check sites. A browser independently sends `POST /monitors` to change a check interval and `GET /monitors` to read results. The package serving those endpoints should be able to inspect a header or reject an oversized upload before allocating memory for JSON. It should also be able to serve a second request on the same connection without recovering bytes accidentally consumed while reading the first.

| Layer | Owns |
| --- | --- |
| Transport | Bind, accept, byte transfer, socket options, optional transport security |
| Proposed `std::http` connection | Request syntax, message boundaries, bounded decoding, response framing and exchange order |
| Third-party server package | Accept and dispatch loops, connection admission, deadlines, workers, handler contract, routing, middleware and shutdown |
| Monitor application | Configuration validation, authorization decisions, persistence, probe scheduling and dashboard data |

Today `std::tcp::listener.accept()` returns an owned stream. The current HTTP request carries an outbound URL and client options, its method enum covers six verbs, and its response represents a client result. Those types continue to serve outbound probes. [TCP listener](https://github.com/lang-gti-official/gti/blob/30796f969ea00d65a051d980d26df4b1f07fb46a/stdlib/std/tcp.gti#L983-L1001) · [HTTP client types](https://github.com/lang-gti-official/gti/blob/30796f969ea00d65a051d980d26df4b1f07fb46a/stdlib/std/http.gti#L524-L553)

## Non-goals

The first version is an HTTP/1.1 origin-server building block. The server package supplies deployment policy, Date generation where required, TLS configuration, authentication, content negotiation and JSON. HTTP/1.0 compatibility, HTTP/2 and HTTP/3, tunnel or upgrade handoff, concurrent in-flight exchanges, nonblocking resumption, and indefinite streaming responses need separate contracts. A fixed-size dashboard response and streamed request ingestion are in scope.

## Guide-level design

Proposed GTI, inside a package function that returns an appropriate `expected`. Here `socket` is a stream from the package's accept loop. `route` is package code. It can read the request body through the connection and returns a reply holding a response head and owned bytes.

```gti
mut auto conn = ?std::http::server_connection<std::tcp::stream>::open(
    std::move(socket), limits);
while (true) {
  auto next = ?conn.read_head();
  if (!next.has_value()) { break; }
  auto& request = next.value();
  auto reply = ?route(request, conn);
  auto after = ?conn.send(reply.head(), reply.bytes(),
                          std::http::connection_policy::automatic);
  if (after == std::http::disposition::close) { break; }
}
```

A GET handler can inspect `request.method_text()` and `request.raw_target()` and reply immediately. A POST handler can check the media type and declared length, call `send_continue()` if needed, and loop over `read_body(scratch)` until it returns zero. The package enforces its smaller JSON limit even for chunks with no declared total. It can send a final rejection immediately. Production dispatch inspects errors from `read_head` or `read_body` to decide whether a close-only error response is possible. Using `?` as above instead elects to close on error.

### Proposed public surface

Signatures below describe the API contract. Accessors that return a span or text view borrow the named receiver. Mutable methods operate on a single exclusively accessed connection.

| Surface in `std::http` | Contract |
| --- | --- |
| `server_connection<S>::open(S stream, server_limits limits) -> expected<server_connection<S>, server_error>` | Move-only owner. Requires `std::io::reader<S>` and `std::io::writer<S>`. Validates limits, performs no network I/O. An unsuccessful open drops the transferred stream once. |
| `read_head() -> expected<optional<request_head>, server_error>` | Read one head. Empty optional means orderly EOF between exchanges. The returned head owns its metadata. |
| `request_head` | `method_text()`, `raw_target()`, `target_form()`, `headers()`, `content_length() -> optional<size_t>`, `expects_continue() -> bool`. Method spelling is case-sensitive and extensible. The raw target includes the query and preserves percent-encoded bytes. |
| `field_block` | Ordered immutable fields. `size()`, `name_at(i)`, `value_at(i)` provide zero-copy inspection for in-range indices. `find_next(name, start) -> optional<size_t>` matches ASCII case-insensitively at or after the given index. Duplicate occurrences remain distinct. |
| `read_body(mut mutable_span<uint8_t>& dst) -> expected<size_t, server_error>` | Fill part of a nonempty caller buffer with decoded message-body octets. Zero means end of this body, including a body absent by framing. Empty destinations yield a local argument error. |
| `send_continue() -> expected<void, server_error>` | Send and flush one 100 response for a supported pending expectation. The caller can instead send a final response. |
| `response_head::create(uint16_t status) -> expected<response_head, server_error>`, `add_header(string_view name, string_view value) -> expected<void, server_error>` | Build an owned final response head. Copy validated names and values in insertion order, including repeated Set-Cookie fields. Failed additions leave the builder unchanged. |
| `send(response_head& head, span<uint8_t>& body, connection_policy policy) -> expected<disposition, server_error>` | Validate the complete final response, write it, and flush before success. Borrow binary body bytes only during the call. `automatic` permits safe reuse and `close` forces closure. Result is `reusable` or `close`. |
| `send_error(uint16_t status) -> expected<void, server_error>` | Available once after an eligible peer-protocol error. Emit a minimal final 4xx/5xx response with zero body and close semantics. The operation has no caller-provided header or wire text. |
| `server_limits`, `server_error` | Finite per-connection resource policy and a typed failure with category, phase, optional underlying `std::io_errc`, and whether a close-only error reply is still permitted. |

## Semantic rules

**One exchange at a time.** Opening enters the between-requests state. Reading a head transitions to an active exchange. Repeated body reads consume its framing. A successful final send returns to between-requests only if reuse is safe. Otherwise the connection enters a terminal state. A second head before replying, a second final response, and operations after terminal state return a local state error without performing I/O. On a close disposition the encoder signals closure on the wire and refuses further exchanges. The package promptly drops the owner to close the underlying stream. An unread positive-length or unfinished chunked body forces close on an early final response. Drop releases the transport and buffers once, with no implicit drain, response, or blocking flush.

**Limits and framing.** Proposed initial defaults are 8 KiB for the request line, 32 KiB for the whole head including terminators, 100 fields, 1 MiB of decoded request data, 1 KiB per chunk-size/extension line, 8 KiB and 32 fields for trailers, and 64 KiB of aggregate chunk framing and trailers per message. Cap the response head at 32 KiB and 100 fields, checked again before emission. Validate overflow and incompatible limits before opening. These are configurable proposed defaults. Read-ahead has a fixed-size window independent of the declared body length. Enforce each budget progressively, including split delimiters, and reject an over-limit declared length at head time. Output body size is supplied by the package; sending a span requires no body-sized internal allocation.

**Incoming wire profile.** Parse octets, strict CRLF, method token and HTTP version. Require a single valid Host field on HTTP/1.1, reject whitespace before field colons, obsolete folding, prohibited control bytes and invalid framing numbers. Preserve opaque field-value octets and strip only surrounding optional whitespace. Accept origin-form and absolute-form, use the absolute target authority for effective authority in that form, and preserve the raw Host occurrence for inspection. Recognize OPTIONS asterisk-form and CONNECT authority-form under their method rules. Expose the authority selected by the target-form rules through a receiver-tied `effective_authority()` accessor so a router can apply its own allowed-host policy consistently. The package can reject CONNECT with a final failure. Do not percent-decode, normalize paths or silently treat extension methods as GET. Recognizable unsupported versions can be rejected with 505.

Accept fixed length, a single final chunked transfer coding, or an absent body when neither framing header is present. Reject combined Transfer-Encoding and Content-Length, any repeated or list-valued Content-Length (deliberately strict), signs, overflow, invalid chunk syntax and framing ambiguities. Unsupported coding chains cannot enter a reusable exchange. Count chunk extensions, delimiters and trailers against framing budgets. Validate trailer field syntax and forbidden fields, consume trailers separately, and discard permitted trailers in this profile. No application depends on dropped trailers for routing, authorization, or integrity. Preserve read-ahead after the final trailer terminator for the next head. Partial EOF in a head, body or chunk terminator is a distinct truncation error.

**Expectations and output.** For `100-continue` on a framed, potentially nonempty body, expose the decision at head time. An attempted body read before the decision is a local state error. Reject unsupported expectations and permit a 417 response. A zero-length body needs no handshake. Response construction accepts final statuses 200–599. The encoder owns Content-Length, Transfer-Encoding, Connection, Trailer and Upgrade, rejects caller attempts to supply them, and emits a computed length for ordinary replies. On HEAD, the provided body represents the corresponding GET content for length calculation and zero body bytes are written. For 204 and 304 require an empty span and omit Content-Length. For 205 require an empty span and send length zero. Refuse successful CONNECT responses in this profile. Error replies also respect HEAD. Response headers must reject CR/LF, invalid tokens and forbidden controls before any write. A peer's `Connection: close` token, explicit close policy or unfinished input body precludes reuse. Never advertise a protocol switch.

**Failure boundaries.** Distinguish configuration/argument errors, wrong state, malformed peer input, unsupported protocol features, each limit class, truncation and transport failure. Invalid local responses can be corrected before committing any bytes. On a peer syntax/limit error before final-response output the decoder stops consuming input; only a single best-effort error reply or drop remains. A failed continue, write, flush, or transport read is terminal. Short successful writes advance only by their accepted prefix; zero progress on nonempty output is a failure. No public retry or replay after partial output. Transports use their existing error mapping. Frameworks requiring a total deadline must supply a deadline-enforcing stream adapter or external cancellation facility. A per-syscall socket timeout cannot by itself bound time across repeated successful short reads.

## Compiler and tooling design

Implement the protocol in ordinary GTI against the existing structural reader/writer contracts on one duplex owner. Use a non-generic parser/encoder for byte accounting and wire rules where feasible, with a small generic I/O driver. This permits deterministic tests with user-defined streams and leaves room for a TLS wrapper exposing the same operations. No new compiler syntax, nominal borrow exemption, runtime HTTP listener, handler trampoline, or libcurl server dependency is proposed. Publish public declarations, documentation and examples through the normal stdlib/tooling pipeline.

### Language capability audit

- Use move-only resources, mutable receivers, `expected`, `optional` and prefix `?` for ownership, recoverable failures and clean EOF. Pattern matching on a payload enum is available if the implementation uses typed states. The package can convert protocol errors to its own error domain explicitly.
- Return an owned request head so the handler can inspect it across body reads and connection reuse. Store bounded owned bytes plus validated offsets, or independently owned field records. Materialize receiver-tied views on demand. Recent borrowed-container support makes views over distinct *external* owners possible; it supplies no proof for a self-referential moved record. No span may survive reuse of the buffer it borrows.
- Reader/writer concepts and checked caller-provided spans permit user-defined transports and binary bodies today. A concrete transport can be configured with chrono durations before ownership transfer. Proposed erased stream adapters are optional future integrations. A package may move a connection into a worker only when its transport and stored fields satisfy GTI transfer rules. Shared concurrent access to a single TCP owner is outside the contract. No new lifetime syntax, global async facility or erased duplex abstraction is prerequisite. [Borrowed containers](https://github.com/lang-gti-official/gti/pull/425) · [Fallible accessor borrowing](https://github.com/lang-gti-official/gti/pull/633) · [Conditional payload patterns](https://github.com/lang-gti-official/gti/pull/652) · [Current byte I/O contracts](https://github.com/lang-gti-official/gti/blob/30796f969ea00d65a051d980d26df4b1f07fb46a/stdlib/std/io.gti#L46-L76) · [Separate stream composition proposal](https://github.com/lang-gti-official/rfcs/pull/11)

## Compatibility and migration

This is additive under `std::http`. Existing clients keep their URL model, methods, redirect policy and native response types. Existing TCP listener code can transfer an accepted stream to the new connection. Incoming header lookup and response emission preserve repeated fields. A framework can layer normalized URIs, custom method enums or convenience JSON APIs above the raw protocol view. A TLS wrapper may be used once it supplies the stream contract and negotiates HTTP/1.1.

## Safety and correctness

The connection is the sole owner of read-ahead and the exchange state. Store the active method semantics and persistence decision independently of the returned head's lifetime. Internal arithmetic checks run before allocating, indexing or adding cumulative sizes. Strict wire acceptance, ordered field occurrences and a single authority for message length prevent the package from accidentally reinterpreting leftover bytes as a fresh request. Verify the compiler rejects use of a view after its head is dropped or moved and overlapping mutable operations on one connection. A disconnected peer or abandoned exchange must release all owned resources exactly once.

## Performance and resource costs

Target linear scanning in received octets, including a peer delivering one byte at a time. Keep scan offsets across refills, bound scratch per connection and write body spans directly. Benchmark a small persistent GET, short JSON POST, fragmented heads, streamed uploads near the limit, and rejected requests. Compare a package dispatching through this API with the same exchange over a direct byte-stream codec. Record throughput, tail latency, peak live bytes, allocations, syscalls, optimized text size and build time with one and several transport types. Demonstrate bounded memory as upload sizes and request counts grow. No measurements exist for this draft.

## Alternatives and tradeoffs

A standard `listen/serve(handler)` would be convenient for a single server style but would choose handler ownership, scheduling and shutdown conventions that competing packages should be free to explore. An HTTP-specific listener returning `server_connection` would merely wrap today's accept and open calls and would favor TCP over TLS or test streams. A public incremental bytes-in/events-out codec would better serve event loops; it needs stable consumed-prefix and partial-output contracts. Keep the internal codec separable and reconsider a public interface with an actual nonblocking consumer. Buffering an entire request in `read_request()` simplifies small JSON applications but prevents early rejection and complicates Expect handling. A framework can provide that helper over bounded `read_body`.

## Unresolved questions

1. Is fixed-length response output sufficient for the first external consumer, or does it need a separate streaming writer with explicit finish and abort? Streaming downloads and SSE would justify the larger API.
2. Should a zero-copy lookup for individual header values be exposed alongside indexed access at launch? Prove its lifetime through an optional return; indexed access already handles missing and repeated fields.
3. Confirm the proposed limit defaults against representative browser requests and production proxy settings. Determine whether deployments need validated trailer access or a HEAD-only length setter before stabilizing the surface.
4. Confirm whether the intended server package uses blocking workers. If it requires event-loop integration at launch, design and validate resumable input **and** output before accepting this blocking profile.

## Implementation plan

1. Implement byte-level request-head decoding and ordered field access in GTI. Prove the ownership contracts, split-input behavior, strict limits and request-target forms with a scripted transport.
2. Deliver the first runnable exchange on an accepted duplex stream with bodyless GET and fixed-length responses. Exercise ordered writes, flush failure, keep-alive and close policy on loopback.
3. Complete bounded fixed-length and chunked input, trailers, continuation handling, early rejection, typed errors and adversarial fragmentation. Keep persistent connections disabled for any incomplete framing path.
4. Prove the package boundary with a separate package fixture implementing `GET /monitors` and `POST /monitors`, then document the stable interface. Route matching, handler registration and JSON live in that package. Track implementation in GTI after a design decision.

## Validation and release criteria

- Drive the codec with an unrelated GTI duplex type. Split representative messages at every byte boundary, coalesce two requests into one read, force short writes, and compare exact emitted bytes. Exercise peer EOF before and during every phase, duplicate headers, non-UTF-8 payloads, case-sensitive methods, HEAD, 204, 205, 304, unsupported expectations and versions, bad lengths, forbidden trailers, overflow, and limit edges.
- Assert no output on local preflight errors. Inject read/write/flush failures before and after partial progress, check close-only behavior, and prove an ambiguous exchange never admits a subsequent request. Test borrowed accessor rejection after move/drop, one-time cleanup and resource bounds.
- On supported macOS and Linux LLVM targets, run a real third-party package against a loopback socket on a dynamically assigned port. Send two requests in one connection, confirm that a rejected POST cannot block waiting for its body, and independently use the existing `std::http::client` as an interoperability peer. Include toolchain API discovery, source documentation, and the performance evidence described above. Release claims require implementation and validation under GTI's normal process.

## Decision record

Draft for discussion. Acceptance and implementation are pending.

## References

- GTI's shipped TCP line-server example demonstrates package-owned service state and byte-stream handling. [TCP example](https://github.com/lang-gti-official/gti/blob/30796f969ea00d65a051d980d26df4b1f07fb46a/examples/193-tcp-line-server.gti)
- The HTTP/1.1 specification defines request targets, field parsing, framing and connection management. The HTTP semantics specification defines methods, expectations, status codes and representation metadata. [RFC 9112](https://www.rfc-editor.org/rfc/rfc9112.html) · [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html)
- GTI's standard-library ownership guidance and runtime performance requirement inform the split between source-defined protocol and host transport. [Standard library and runtime](https://github.com/lang-gti-official/gti/blob/30796f969ea00d65a051d980d26df4b1f07fb46a/docs/architecture/standard-library-and-runtime.md) · [ADR 012](https://github.com/lang-gti-official/gti/blob/30796f969ea00d65a051d980d26df4b1f07fb46a/docs/decisions/012-outcome-first-systems-readiness.md)
