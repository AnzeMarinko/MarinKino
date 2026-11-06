# Raspberry Pi: performance and diagnostics

## Read-only measurement

From the project directory on the Pi:

```sh
sudo bash scripts/rpi_metrics.sh
```

The command takes about 20 seconds. It prints RAM/swap, CPU and I/O pressure,
temperature, firmware throttling flags when available, container memory/CPU,
OOM/restart counters, disk capacity and process names. It does not print
environment variables, process arguments, application logs or secrets.

Capture once with the site idle, once while uploading a representative photo,
and once during scheduled maintenance. Label each output with the workload.
`docker stats` is a sample, not peak memory history. `OOMKilled` describes the
current container state; the kernel count provides another limited signal.
The first `vmstat` row averages time since boot; subsequent rows are samples.
The script does not generate load or change settings.

## Static files and blog images

The app build produces `/static/v/<content digest>/...` and precompressed gzip
files. Its Nginx image copies exactly that app image's static release. Immutable
cache headers apply only to versioned paths; legacy paths require revalidation.
Keep the app and Nginx image from the same deployment when restoring a snapshot.
HTTP/2 is enabled on the HTTPS website.

Plyr's reset clip is served locally as `vendor/blank.mp4`, including its
versioned URL. Source: `https://cdn.plyr.io/static/blank.mp4`; SHA-256:
`5747997d80825cbafcdbe5ab97d7b5502c06b1aae85fed9610845348b3da4d98`.
This avoids an external media request when switching video sources.

New blog uploads retain originals and add WebP display sizes. Existing photos
are prepared sequentially by `python -m blog_images --prepare-existing` in a
resource-limited container during the standard update procedure. Preparation
does not replace original photos or rewrite posts. HTTP requests only read
prepared image metadata; they do not resize images. Unprepared images retain
the original URL until the preparation command succeeds.

## Background work

`python -m serve` starts two bounded consumers in the same process: one for
mail and one for movie archives. A long archive cannot occupy a Waitress thread
or delay password-reset mail. The queue is stored in `data/jobs.sqlite3`, has
at most 128 pending/running records, and accepts at most 2 MiB per payload.
The database and its backups contain private mail data and must stay private.

Queued work survives a restart. Interrupted archives are prepared again.
Interrupted SMTP delivery becomes `uncertain`: it is not automatically resent,
because the server may already have accepted the message. An administrator
must verify delivery before arranging another send. A failed blog campaign
can be requested again; completed language groups are skipped. SMTP cannot
provide exactly-once delivery across a connection loss or partial rejection.
Terminal jobs discard message payloads; their status records expire after
seven days. The editor distinguishes queued/running/done/failed/uncertain.

Both `python -m serve` and `python src/app.py` start the same consumers.
Isolated tests call `JobStore.run_once` with explicit handlers.

## Statistics and caches

Public blog views are daily aggregate counts, not unique visitors. No visitor
IP is stored in these counts and no geolocation service is contacted. The
update procedure runs `python -m analytics_privacy` to convert old per-IP view
hashes without changing totals and remove legacy geolocation keys. It does
not touch authentication records. Existing backups keep their own retention.

Known HTTP paths are grouped by route pattern; unmatched requests share one
counter. Dashboard aggregates are cached for 30 seconds. Blog source caching
uses file revisions and returns independent copies; only sanitized Markdown
is cached, never complete HTML with cookies, CSRF tokens or CSP nonces.

## Verification before publication

Run unit tests and opt-in browser checks. The normal deployment additionally
builds the ARM images, validates Nginx configuration and checks the isolated
runtime before switching containers. Those container checks must run on a
machine with Docker; Python configuration tests do not replace `nginx -t`.
