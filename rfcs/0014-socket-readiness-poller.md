# RFC 0014: Multi-socket readiness polling for std::tcp

| Field | Value |
| --- | --- |
| Status | draft |
| Authors | @gti-language-official (with Claude) |
| Created | 2026-11-26 |
| Updated | 2026-11-26 |
| Area | stdlib |
| Proposal | https://github.com/lang-gti-official/rfcs/pull/15 |
| Decision | pending |
| Implementation | none |
| Supersedes | none |
| Superseded by | none |

## Summary

Add `std::tcp::poller`, a standard readiness poller that waits on many
`std::tcp::stream` and `std::tcp::listener` sockets at once. A package
registers sockets it keeps owning under tokens it chooses, then calls
`wait(events, timeout)` and receives level-triggered readiness events
carrying those tokens. The poller stores descriptors only inside trusted
standard-library source, never exposes them, and cannot report readiness for
a socket that was closed or dropped while registered. With it, a third-party
package can run one single-threaded event loop over many connections, for
example an HTTP/1.1 server built on `std::http::server_codec` (RFC 0011).

This is a draft. Nothing here is implemented.

## Motivation and goals

RFC 0011's server codec ([rfcs#12](https://github.com/lang-gti-official/rfcs/pull/12))
is on GTI `main` (gti#671). It performs no I/O by design: a server decides
when to read and write. `std::tcp` already offers nonblocking mode
(`set_nonblocking`) and per-socket `wait_readable`, `wait_writable` and
`wait_acceptable` with chrono timeouts, but nothing waits on several sockets
at once.

A package cannot build that itself. `std::tcp` deliberately hides
descriptors: only trusted standard-library source can name
`gti_internal::tcp_socket_handle` (GTI-S2058), so applications cannot adopt or
forge a descriptor. That boundary is correct and should stay. The cost is
that gti#671's two-client fixture
(`tests/slow/project/http_server_connections`) has to take turns: it blocks
on one connection's `wait_readable` while the other may be ready, so a slow
or stalled client delays the rest.

Goals:

- One thread, one poller, many connections, with no busy waiting.
- A package keeps owning its sockets and per-connection state, and chooses
  the token that identifies each registration.
- No descriptor reaches application code, and a stale registration can never
  produce an event for an unrelated socket that reused its descriptor.
- The same GTI API on every supported POSIX target (macOS and Linux today).
- Checkable by the current compiler. No new language feature.

Success: a package can serve two or more concurrent HTTP connections on one
thread, one stalled mid-header while another completes and a third waits for
write capacity, without the turn-taking in gti#671's fixture.

## Non-goals

- A scheduler, executor, task system, async/await or futures.
- Timers beyond the `wait` timeout. A loop that needs deadlines computes the
  next one and passes it as the timeout.
- TLS, UDP, Unix-domain sockets, files and pipes. The design leaves room for
  more readiness sources later, but v1 accepts only `std::tcp` sockets.
- Edge-triggered and one-shot delivery.
- A cross-thread waker in v1 (see Unresolved questions).
- Stream composition. RFC 0010 ([rfcs#11](https://github.com/lang-gti-official/rfcs/pull/11))
  owns readers, writers and adapters. A poller only reports readiness, and
  any stream adapter may be driven by it.

## Guide-level design

```gti
import std.tcp;
import std.chrono;
import std.span;

expected<void, std::tcp::errc> serve(mut std::tcp::listener& server) {
  mut auto poll = ?std::tcp::poller::create();
  ?server.set_nonblocking(true);
  ?poll.add(server, uint64_t(0));                       // listener: acceptable

  mut std::tcp::readiness events[64] = {};
  while (true) {
    mut auto out = std::mutable_span<std::tcp::readiness>(events);
    std::size_t count = ?poll.wait(out, std::chrono::nanoseconds(1_000_000_000i64));
    for (mut std::size_t i = 0; i < count; i++) {
      auto event = events[i];
      if (event.token == uint64_t(0)) {
        // accept() until would_block, then register each connection:
        //   ?poll.add(connection, token, std::tcp::interest::readable);
      } else {
        // event.readable / event.writable / event.closed / event.failed
        // drive that connection; switch to writable interest when a send
        // reports would_block:
        //   ?poll.modify(token, std::tcp::interest::writable);
      }
    }
  }
}
```

- `std::tcp::poller::create()` returns `expected<poller, errc>`.
- `add(stream&, token, interest)` registers a connected stream. It fails with
  `invalid_argument` for a token already in use, and with `not_open` for a
  closed stream.
- `add(listener&, token)` registers a listener for acceptance.
- `modify(token, interest)` changes a stream's interest.
- `remove(token)` deregisters.
- `wait(events, timeout)` blocks until at least one registration is ready
  or `timeout` elapses. It fills the caller's `mutable_span<readiness>`
  and returns the number of events written: zero on timeout, never more
  than the span's size. `wait(events)` waits without a timeout.
- `readiness` is a plain copyable value:
  - `token`, the registering package's choice;
  - `readable` (data, end of stream, or a pending connection for a listener);
  - `writable`;
  - `closed` (the peer hung up);
  - `failed` (the socket holds a pending error; the next operation reports it).

Failure cases:

- A token already in use is `invalid_argument`. So is an unknown token to
  `modify` or `remove`, or a negative timeout.
- Registering a moved-from or closed socket is `not_open`.
- A host refusal to allocate is `resource_exhausted`. So is exceeding the
  host's per-wait descriptor limit.
- A socket closed or dropped while registered produces no further events (see
  Semantic rules). Its token stays reserved until `remove`.

## Semantic rules

### Registration and ownership without exposing descriptors

Recommendation: **mio-style registration with a runtime identity check, and
no retained borrow.**

- `add` takes the socket by read-only reference, `std::tcp::stream&` or
  `std::tcp::listener&`. It stores no reference. Inside trusted std source it
  records three things:
  - the socket's descriptor (`tcp_socket_handle::get()`);
  - the socket's *runtime identity*, a 64-bit value the runtime assigns when
    it creates a descriptor and forgets when it closes it;
  - the token and interest.
- **Moving** a registered socket changes nothing: a move transfers the same
  descriptor, so the registration follows the socket, including to another
  owner or thread.
- **Closing or dropping** a registered socket is permitted and safe. The
  runtime clears the identity before `close(2)`. `wait` compares each
  registration's identity before and after the host wait. An entry whose
  identity no longer matches is skipped and produces no event, even if the
  descriptor number has meanwhile been reused by an unrelated socket. The
  token stays reserved until `remove`, so a package's token-to-state map
  never sees a recycled token by surprise.
- **`mut` access is not required**, because registration changes no state of
  the socket. A package may therefore register a socket, keep using it
  through `mut` methods, and move it into per-connection state.
- **Poller drop** releases only the poller's own storage (and, with a kernel
  backend, its kernel object). It never closes registered sockets: the
  package owns them.

Why not a borrow that makes misuse impossible? Under
`docs/language/ownership-and-lifetimes.md`, a poller holding `stream&<s>`
for each registration would keep each stream shared-borrowed for `s`. Every
`send`, `receive` or `close` needs `mut` access, so a borrow-retaining poller
would forbid exactly the operations an event loop performs. A
`mut stream&<s>` registration is worse: the loop could reach the socket only
through the poller. Making the poller own registered sockets (a slab returning
`mut stream&<this>`) is checkable today. It also moves the package's
connection objects into the standard library and separates socket ownership
from the package's per-connection state, which is what gti#671's fixture
models. The runtime identity check keeps the package in charge of ownership
and makes stale registrations harmless. It needs no new language feature.

Consequence: misuse that a borrow-based design rejects at compile time
(using a token after its socket is dropped) is here a defined, harmless
runtime outcome: no events. Compile-time rejections still cover:

- copying or sharing a poller (it is move-only and `no_share`);
- forging a socket from a descriptor (GTI-S2058);
- registering something that is not a `std::tcp` socket;
- calling `add`, `modify`, `remove` or `wait` on a read-only poller.

### Interests and triggers

- `std::tcp::interest` is an enum class: `readable`, `writable` and
  `read_write`.
- A listener registration always has acceptance interest, which is reported
  as `readable`.
- Delivery is **level-triggered**: every `wait` reports each registration
  that is ready at that moment. A package that does not drain a socket sees
  it again, and a writable-interested socket is reported while send capacity
  exists.
- Level-triggering is recommended because it is correct when a package reads
  only part of the available data, as the HTTP codec does with bounded
  buffers. Edge-triggered delivery would require reading until `would_block`
  on every event and is easy to misuse. Edge-triggered and one-shot modes can
  be added later as interest flags.
- `closed` and `failed` are reported regardless of interest. For a
  registration with no ready interest, they are its only events.

### Waiting

- The caller owns the event storage, a `mutable_span<readiness>`. A wait
  performs no allocation, its bound is the span's size, and the loop can
  `modify` or `remove` registrations while iterating copied events. A
  poller-owned buffer returning a borrowed span would keep the poller borrowed
  during iteration and forbid those calls.
- The timeout is `std::chrono::nanoseconds`:
  - zero polls without blocking;
  - a negative value is `invalid_argument`;
  - the host granularity rounds positive timeouts up to whole milliseconds;
  - `wait(events)` waits indefinitely.
- Interrupted host waits (`EINTR`) are retried inside the runtime with the
  remaining time, as every other `gti_rt_tcp_*` entry does. A timeout returns
  `0`, not an error, so the loop can run its own deadlines.
- If more registrations are ready than the span holds, the rest are reported
  by the next `wait`. Level-triggering guarantees they are not lost.
  Registration order rotates between waits so that a small span cannot starve
  later registrations.
- No waker in v1. A cross-thread waker needs a shareable handle beside a
  `no_share` poller, plus an internal pipe or `eventfd` registration. That is
  separable and deferred (see Unresolved questions).

### Platforms and runtime boundary

- Behind the existing private TCP runtime boundary (`runtime/include/gti/tcp.h`),
  v1 adds three entries:
  - `gti_rt_tcp_identity_v1(int32_t descriptor, uint64_t* output)`: the
    current identity;
  - `gti_rt_tcp_poll_v1(entries, count, timeout_ms, output_ready)`: one host
    wait over call-bounded entries of `{descriptor, interest, identity,
    ready}`;
  - an identity update folded into the existing create and close entries.
- **v1 uses `poll(2)` on both macOS and Linux**, so both targets share one
  implementation and identical semantics.
- kqueue and epoll are an implementation change behind the same GTI API,
  made when measurement shows `poll(2)`'s per-wait O(n) cost matters. The
  runtime then owns a kernel object per poller, and the identity check
  remains necessary because kqueue and epoll registrations also outlive a
  descriptor's number.
- Windows remains unsupported, as for `std::tcp` today.

### Errors

The poller reports `expected<T, std::tcp::errc>`, the same error type as
every `std::tcp` operation. `std::tcp::io_error` already maps `errc` to
`std::io_errc` for stream adapters, and nothing in a poller needs a separate
type. No new `errc` value is required:

- duplicate or unknown token: `invalid_argument`;
- closed socket: `not_open`;
- host limits: `resource_exhausted`;
- other host failures: `failed`.

## Compiler and tooling design

None. This is standard-library and runtime work:

- `stdlib/std/tcp.gti` gains `interest`, `readiness` and `poller`.
- `runtime/include/gti/tcp.h` and `runtime/src/tcp.cpp` gain the identity
  table and the poll entry.
- The stdlib surface manifest and `docs/language/tcp.md` and
  `docs/language/http.md` (Serving HTTP/1.1) document them.

The compiler already provides everything the design uses:

- move-only `no_share` owners;
- the GTI-S2058 trusted-handle rule;
- `mutable_span` of a plain value type;
- `expected`;
- the LLVM backend's native call ABI for `gti_rt_*` entries.

LSP and formatter impact is limited to the new names.

## Compatibility and migration

Purely additive. Existing `wait_readable`, `wait_writable` and
`wait_acceptable` stay. gti#671's fixture keeps working, and a
poller-driven variant shows the new loop. The runtime entries are new
versioned symbols. The identity update inside existing create and close
entries changes no observable behaviour of those entries.

## Safety and correctness

Invariants:

1. **No descriptor reaches application code.** The poller stores descriptors
   only in private fields of trusted std source, and events carry only
   package tokens.
2. **No misattributed readiness.** An event is produced only for a
   registration whose identity matched both before and after the host wait.
   The runtime clears an identity before closing the descriptor and assigns a
   fresh one after creating it. A descriptor number reused during a wait
   therefore yields no event for the old token: it can wake `wait` spuriously,
   but cannot misdirect a readiness report.
3. **No dangling access.** A poller retains no reference to a socket, so
   moving, closing or dropping a registered socket cannot leave the poller
   pointing at freed GTI storage.
4. **Bounded output.** `wait` writes at most the span's size.
5. **Cleanup.** Dropping a poller closes no package socket.

Readiness is a hint, as on every host. A `readable` event followed by a
receive that reports `would_block`, for example after another thread used the
socket, is correct behaviour, and packages must keep handling `would_block`.
These invariants are tested by registering, moving, closing, dropping and
reusing descriptors (see Validation), not inferred from a demonstration.

## Performance and resource costs

- **Per registration:** one 24-byte entry in a poller-owned vector.
- **Per wait:** one `poll(2)` over all registrations, so O(n) kernel and
  runtime work, plus two identity-table lookups per entry under one lock.
  This fits tens to a few hundred connections, the target of a third-party
  HTTP package.
- The identity table adds one map insert per socket creation and one erase
  per close. Each socket operation stays O(1).
- kqueue and epoll would make waits O(ready). Switching is an implementation
  change gated on measurement.
- No measurement exists yet. Acceptance should compare a poller-driven
  loopback server against the turn-taking fixture: latency for a fast client
  while another is stalled, and wait cost at 10, 100 and 1000 idle
  registrations.

## Alternatives and tradeoffs

- **Borrow-retaining registration** (`poller<lifetime s>` holding
  `stream&<s>`): compile-time protection against stale use, but it forbids
  the `mut` operations the loop needs. Rejected.
- **Poller-owned sockets (a slab):** sound and checkable, but it takes
  ownership away from the package and splits socket from connection state.
  It remains a possible convenience layer on top of this design.
- **Exposing descriptors to packages:** this undoes GTI-S2058 and lets
  packages forge or double-close descriptors. Rejected.
- **Edge-triggered default:** fewer events, but incorrect for partial
  readers. Deferred as an opt-in.
- **kqueue and epoll from v1:** better scaling, but two implementations and
  a kernel object to own. Deferred behind the same API.
- **Keep turn-taking:** forces a stalled client to delay others. Rejected
  for servers.

## Unresolved questions

- **Waker.** Should v1 add a `poller::waker()` returning a `share`-able
  handle that interrupts `wait` from another thread? Recommendation: defer to
  a follow-up that also settles how a waker is reported (a reserved token or
  a `woken` result).
- **Event delivery for stale entries.** Should a dropped socket's
  registration produce a single `closed` event before going silent?
  Recommendation: no. The package dropped it and knows; a report would
  complicate token reuse.
- **Interest representation.** Is an enum class enough, or should `interest`
  be a flag set so edge-triggered and one-shot can be added without new
  enumerators? Recommendation: enum class now, and revisit with those modes.
- **Generic readiness sources.** Should other future std owners (pipes,
  child process streams) register through a shared readiness concept?
  Recommendation: yes eventually, through a trusted-only protocol, not in v1.

## Implementation plan

1. **Runtime:**
   - identity table in `runtime/src/tcp.cpp`, assigned in the connect, listen
     and accept entries and cleared in close;
   - `gti_rt_tcp_identity_v1` and `gti_rt_tcp_poll_v1` (`poll(2)`);
   - header contract.
2. **stdlib:** `std::tcp::interest`, `readiness` and `poller` in
   `stdlib/std/tcp.gti`; the surface manifest; `docs/language/tcp.md`.
3. **Package evidence:** a poller-driven variant of gti#671's
   `http_server_connections` fixture (a `web` library package plus an app),
   and `docs/language/http.md`'s serving section showing the loop.
4. **Later, gated on measurement:** kqueue and epoll backends, a waker,
   edge-triggered and one-shot modes.

Implementation tracking: the GTI implementation PR will link back here.

## Validation and release criteria

- **UI and project tests:**
  - registration, readiness and timeout (zero, positive and negative);
  - `modify` between readable and writable, and `remove`;
  - duplicate and unknown tokens;
  - a listener's acceptance;
  - a moved registered socket;
  - a closed or dropped registered socket yielding no events, including when
    its descriptor number is reused;
  - span bounds and rotation across waits.
- **Compile-time rejections:** a copied poller, a poller shared across threads,
  a forged handle, and a mutation through a read-only poller.
- **Event loop:** one thread and one poller drive at least two concurrent
  HTTP connections through `std::http::server_codec`. One connection stalls
  mid-header while another completes, and a backpressured writer resumes on
  writable readiness, across a library package and an app.
- **Platforms:** LLVM on macOS arm64 and Linux x64.
- **Docs:** `docs/language/tcp.md`, `docs/language/http.md` and the stdlib
  surface manifest.

## Decision record

No design decision yet.

## References

- [RFC 0011, HTTP/1.1 server connections](https://github.com/lang-gti-official/rfcs/pull/12):
  the codec this poller lets packages drive concurrently.
- [RFC 0010, composable streams](https://github.com/lang-gti-official/rfcs/pull/11):
  reader and writer composition, complementary to readiness.
- GTI `stdlib/std/tcp.gti` and `docs/language/tcp.md`: the current socket
  owners, nonblocking mode, per-socket waits and the GTI-S2058 descriptor
  boundary.
- GTI `tests/slow/project/http_server_connections` (gti#671): the
  turn-taking fixture this design replaces.
- GTI `docs/language/ownership-and-lifetimes.md`: why a retained borrow would
  forbid event-loop mutation.
- mio's `Registry::register(&mut source, token, interest)` and level/edge
  semantics, Rust's `polling` crate and POSIX `poll(2)`: prior art for token
  registration and level-triggered readiness.
