---
layout: ../../layouts/Doc.astro
title: 'Multiple URLs and parallel transfers'
description: 'Send several requests with Curlimp, pair URLs with output files, limit parallel transfers, and export an ordered JSON array with Docker or native downloads.'
slug: multiple-urls
section: Usage
lead: 'Send a batch with one command, choose where each response goes, and opt into bounded concurrency.'
---

## Start with sequential requests

List URLs on the same command line. Transfers run one at a time by default, in input order. Line breaks with `\` are only for readability:

```sh
curlimp -sS -i https://httpbin.org/status/200 https://httpbin.org/status/502
```

Every URL uses the same request options and browser profile. Flags can appear before or after URLs. Select a positional browser name before the first URL, or use `--impersonate PROFILE` anywhere. `--url URL` also adds a URL to the list.

HTTP errors are responses, not transfer failures, unless you use `-f` or `--fail-with-body`.

## Choose an output for each URL

The first `-o` belongs to the first URL, the second to the second URL, and so on, regardless of where each option appears:

```sh
curlimp -sS -i \
  https://httpbin.org/status/200 https://httpbin.org/status/502 \
  -o test1.txt -o test2.txt
```

An output is optional. Missing destinations use stdout; `-o -` explicitly selects stdout:

```sh
# Print the first response; save only the second.
curlimp -sS -i \
  https://httpbin.org/status/200 https://httpbin.org/status/502 \
  -o - -o response-502.txt

# Save only the first response; print the second.
curlimp -sS -i \
  -o response-200.txt \
  https://httpbin.org/status/200 https://httpbin.org/status/502
```

Extra destinations are ignored with a warning unless silent mode is active. Repeating the same output path is not an append operation: transfers can overwrite each other's output, especially in parallel. Use different paths.

To keep all ordinary output in one file, use sequential requests and shell redirection:

```sh
curlimp -sS -i \
  https://httpbin.org/status/200 https://httpbin.org/status/502 > responses.txt
```

`>` overwrites the file; `>>` appends. Redirected stdout contains only what the flags select: body by default, headers and body with `-i`, or HEAD headers with `-I`. It is a concatenation, with no extra separator added by Curlimp. With Docker, the host shell handles redirection, so this needs no volume mount:

```sh
docker run --rm juanfontes/curlimp -sS -i \
  https://httpbin.org/status/200 https://httpbin.org/status/502 > responses.txt
```

## Run requests in parallel

`--parallel` (or `-Z`) admits up to 50 active transfers by default. Use `--parallel-max` to choose a smaller limit:

```sh
docker run --rm juanfontes/curlimp \
  --parallel --parallel-max 2 --json-output -sS -i \
  https://httpbin.org/status/200 https://httpbin.org/status/418 \
  https://httpbin.org/status/502
```

`--parallel-max` alone does not enable parallel execution. Zero selects the default of 50; values above 65535 are clamped to 65535. Negative, fractional, and overflowing unsigned values are rejected. `--no-parallel` disables parallel execution; the last enable/disable flag wins.

Ordinary stdout and shared header output can interleave in parallel. Use distinct `-o` destinations, automatic export files, or `--json-output` when responses need to remain separate. Redirecting parallel stdout to one file does not restore input order.

## Export a batch

`--txt` and `--json-file` create one automatic file per URL. Duplicate URLs get distinct collision-safe filenames. Mount a directory to preserve those files from Docker:

```sh
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" \
  juanfontes/curlimp --parallel --json-file -sS -i \
  https://httpbin.org/status/200 https://httpbin.org/status/418
```

`--json-output` prints one object for a single URL and one array for several URLs. Array members remain in input order even if transfers finish out of order. Each multi-URL object includes a zero-based `transfer_index` and a normalized `url`, alongside the usual status, exit code, and selected response fields. Credentials and fragments are removed from that URL. Invalid URLs use an empty URL field; the index still identifies the input. Query strings are retained and can contain sensitive information.

```sh
# Save one ordered JSON document with the host shell.
docker run --rm juanfontes/curlimp --parallel --json-output -sS -I \
  https://httpbin.org/status/200 https://httpbin.org/status/502 > responses.json
```

Each response can select at most 64 MiB of combined headers and body for JSON. Private temporary files keep payload memory bounded; they require writable temporary storage. The result array is emitted after all transfers finish. A temporary-storage or serialization failure returns 23 and suppresses the aggregate; stdout write failures can leave partial output. Ordinary network failures remain array entries with their own `exit_code`.

See [response exports](../response-exports/) for the schema, binary encoding, storage, and conflicting flags.

## Shared options, cookies, and diagnostics

- Request data, header files, and stdin are prepared once and reused across the batch. Each URL receives the same request body.
- Cookies are shared within the invocation, and `-c` writes one final cookie jar. A sequential request can use eligible cookies from an earlier response. Parallel requests can already be in flight when another response sets a cookie; use sequential requests for dependent login flows.
- `-D headers.txt` opens one header destination for the invocation. `-w` runs once per completed transfer; in parallel, its records follow completion order.
- `--max-time` applies to each admitted transfer, not to the entire batch or its time waiting for a slot.
- Errors go to stderr, with the transfer number for multi-URL requests. `-s` suppresses them; `-sS` shows them.

## Exit status and limits

Sequential execution returns the last transfer's result, so a later success can hide an earlier failure in the process status. Parallel execution retains the first observed transfer failure, which is not necessarily the first URL in input order. Ordinary transfer errors do not stop queued URLs. Fatal setup/resource failures stop the invocation. Export storage and serialization failures return 23 even if a later request succeeds.

Inspect each JSON member's `exit_code` when you need every result. For HTTP error statuses to count as failed transfers, add `--fail-with-body` (retain the body) or `-f` (suppress it).

This release uses one common request configuration. It does not implement `--next`, URL globbing, per-URL profiles, retries, a progress meter, `--parallel-immediate`, or `--parallel-max-host`.
