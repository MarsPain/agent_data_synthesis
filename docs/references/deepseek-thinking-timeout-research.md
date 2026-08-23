# DeepSeek Thinking and Timeout Research

Scope: official DeepSeek documentation only, checked 2026-08-23. This note
does not make a provider request and does not establish the cause of a prior
provider failure.

## Verified facts

### Model identifier

`deepseek-v4-pro` is an official DeepSeek Chat Completions model identifier.
DeepSeek lists it in both its [model catalogue](https://api-docs.deepseek.com/quick_start/pricing/)
and the example response for [`GET /models`](https://api-docs.deepseek.com/api/list-models/).
The catalogue also says that V4-Pro supports both thinking and non-thinking
modes, with thinking enabled by default.

### Disable thinking in Chat Completions

For a raw OpenAI-compatible `POST /chat/completions` request, place the
following field at the top level of the JSON body:

```json
"thinking": {"type": "disabled"}
```

For example:

```json
{
  "model": "deepseek-v4-pro",
  "messages": [
    {"role": "system", "content": "Return strict JSON only."},
    {"role": "user", "content": "..."}
  ],
  "thinking": {"type": "disabled"},
  "response_format": {"type": "json_object"}
}
```

The [Chat Completions reference](https://api-docs.deepseek.com/api/create-chat-completion/)
defines `thinking.type` as `enabled` or `disabled`, defaults it to `enabled`,
and says `disabled` uses the non-thinking model. The
[Thinking Mode guide](https://api-docs.deepseek.com/guides/thinking_mode/)
gives the OpenAI-SDK equivalent:

```python
extra_body={"thinking": {"type": "disabled"}}
```

`extra_body` is SDK-specific. A runner that constructs the HTTP JSON body
itself should send `thinking` as the top-level field, not a nested
`extra_body` field. `reasoning_effort` controls the effort of an enabled
thinking mode; it is not the switch that disables thinking.

In thinking mode, DeepSeek says `temperature`, `top_p`, `presence_penalty`,
and `frequency_penalty` have no effect. Disabling thinking therefore makes the
current judge's explicit sampling settings meaningful again, but it is also a
semantic change from reasoning to non-reasoning judgment.

### Official latency, timeout, and retry guidance

- A queued request remains connected while waiting. DeepSeek sends empty lines
  for non-streaming requests and SSE keep-alives for streaming requests; if
  inference has not begun after ten minutes, the server closes the connection.
  See [Rate Limit & Isolation](https://api-docs.deepseek.com/quick_start/rate_limit/).
- The [FAQ](https://api-docs.deepseek.com/faq) says that non-streaming API
  requests return only after generation completes and that streaming can
  improve interactivity. It does not state that streaming reduces total model
  work or is suitable for a JSON-only judge without a streaming parser.
- For `500`, DeepSeek advises retrying after a brief wait; for `503`, retry
  after a brief wait; and for `429`, pace requests reasonably. See
  [Error Codes](https://api-docs.deepseek.com/quick_start/error_codes/).
- DeepSeek publishes no exact client timeout, retry count, retry-delay formula,
  latency SLO, or statement that non-thinking mode has lower latency in these
  sources.

## What remains unknown

The latest local retry artifact records two sanitized `provider_error`
outcomes for the V4-Pro preflight, but intentionally retains neither the HTTP
status nor the transport exception class. It therefore cannot distinguish a
30-second client timeout from a `500`/`503`, rate limit, network error, or
another provider-side failure. The official material supports the possibility
that a short *total* client deadline can conflict with a queued request, but
it does not prove that this occurred here. Whether the local client's
30-second limit is a total deadline or an idle/read deadline that is refreshed
by provider keep-alives is an implementation-level question, not something
the sanitized artifact answers.

Likewise, disabling thinking is a plausible latency-reduction experiment, not
an official performance guarantee. Because the judge is an admission gate,
its output quality must be re-validated under the non-thinking setting rather
than assumed equivalent.

## Recommendation for the local runner

For a future explicitly authorized attempt, keep the independent
`deepseek-v4-pro` judge but make its request configuration explicit and
replay-bound:

1. Add a judge-only request option that sends
   `"thinking": {"type": "disabled"}` in the raw Chat Completions body;
   record that option in the sanitized authorization/evidence identity. Do not
   rely on the provider default.
2. Increase the judge's 30-second local deadline to a deliberately chosen,
   bounded value (the current local configuration permits at most 120 seconds).
   That value is a local policy choice, not a DeepSeek recommendation; it is
   still shorter than the provider's documented ten-minute queued-request
   window.
3. Apply a bounded delay or exponential backoff between retryable `500`/`503`
   and transport retries. The present no-delay retry does not implement the
   provider's instruction to wait briefly.
4. Preserve the existing fixed, non-source-backed judge preflight. Run it with
   the exact thinking/timeout/retry configuration before any generation spend.
5. Persist only a sanitized failure class (for example `timeout`, `http_503`,
   `http_5xx`, `http_429`, or `transport`) and timing, never prompts,
   responses, credentials, or Workspace source content. This will let a later
   bounded run distinguish timeout from overload without weakening the
   evidence policy.

Changing thinking mode or timeout/retry behavior changes the hash-bound live
configuration. It requires a fresh authorization and a regression/quality
check; it must not be presented as a completed release qualification.

## Official sources

- [DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)
- [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)
- [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)
- [DeepSeek List Models API](https://api-docs.deepseek.com/api/list-models/)
- [DeepSeek Rate Limit & Isolation](https://api-docs.deepseek.com/quick_start/rate_limit/)
- [DeepSeek Error Codes](https://api-docs.deepseek.com/quick_start/error_codes/)
- [DeepSeek FAQ](https://api-docs.deepseek.com/faq)
