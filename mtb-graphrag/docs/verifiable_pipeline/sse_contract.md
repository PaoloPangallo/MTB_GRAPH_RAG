# Current SSE contract

Endpoint: `GET /api/v1/research/pipeline/runs/{run_id}/stream`.
Content-Type: `text/event-stream`. Research feature flag applies; unknown run 404.

Each frame has `id: <sequence>`, `event: <event_type>` and `data: <PublicEvent JSON>`.
The public projection matches the REST event projection. `compact=true` keeps
lifecycle and workload progress fields; it does not change persisted artifacts.

`Last-Event-ID` resumes strictly after that sequence. Missing, invalid or negative
headers start at zero. The server reads SQL pages of 200, draining queued pages
without poll delays. No full-run payload list is loaded for polling.

Completed and historical runs drain their persisted events and close. A worker
finishing during an empty-page read triggers a final read, so the terminal append
is not lost. Active runs poll every 0.2 seconds, heartbeat after 15 seconds and
close after 300 seconds without event activity. The idle deadline resets on data.
Responses use `Cache-Control: no-cache` and `X-Accel-Buffering: no`.

The client validates each PublicEvent before reducer use. A contract-invalid frame
surfaces a controlled error and schedules REST snapshot recovery. Malformed JSON
is discarded under the existing transport policy. REST stage adapters normalize
missing/null historical warning/error/reason arrays before UI consumption.

The pool and live-worker state belong to one backend process. This stream is not
a distributed job coordinator; use a single owner process for a given live-run pool.
