# Render: Delta BTCUSD read-only collector

## Honest service limits

This repository can be prepared for Render, but a **₹0 Render service is not a durable, continuously-running collector**:
- Render Free web services can spin down after 15 minutes without inbound traffic and may restart at any time.
- Free web services have ephemeral local filesystems; local JSONL/gzip archives and SQLite files can disappear after restarts/deploys/spin-down.
- Persistent disks and background workers require a paid compute plan.
- Free Render Postgres is not a durable long-term alternative: it expires after 30 days and has no backups.
- External uptime checks can detect/possibly reduce idle spin-down but do not create an uptime or persistence guarantee.

Sources: https://render.com/docs/free, https://render.com/docs/disks, https://render.com/docs/service-types

## Files added

- `Dockerfile.render-collector`: separate Docker image; leaves the existing dashboard Dockerfile untouched.
- `render_collector_service.py`: supervisor for the existing `delta_collector.websocket_client`, health endpoints and optional webhook alerts.
- `render.yaml`: Free-tier preview Blueprint. It does not create a service until explicitly deployed/authorized.
- Existing collector remains the only Delta WebSocket client; no order code is imported or called.

## Health endpoints

- `/healthz`: liveness only. A 200 means the HTTP process responds, not that market data is fresh.
- `/readyz`: returns 200 only when the collector process is running and the local receive/processing timestamp is fresh; otherwise 503. Point an independent external monitor at this endpoint.
- `/status`: diagnostics; contains no credentials or order controls.

The freshness timestamp is a local receive/processing timestamp, not proof of exchange event time. Market inactivity can be ambiguous; inspect logs and source timestamps before treating a stale alert as an outage.

## Alerting

Set `ALERT_WEBHOOK_URL` in Render Environment to a secret JSON webhook URL. This service emits rate-limited stale-feed, recovery, collector-exit, and supervisor-exception alerts. Configure an independent monitor (for example, an external uptime monitor) against `/readyz` so it can alert when the whole Render service is down. Do not use the public endpoint for sensitive control operations; this service exposes no controls.

## Storage and backup

The Free plan uses ephemeral local storage. **Do not treat local gzip partitions as durable backups.** A paid Render service plus a persistent disk is needed for on-host persistence; it still needs off-host backups. Do not configure a secret or data sink until its access controls and retention are reviewed. Before collecting meaningful research data, select a durable storage target and run an export/restore drill.

## Deployment steps (not performed by these files)

1. Push the repository branch to GitHub only after reviewing the large existing uncommitted changes. Do not stage/commit the whole repo.
2. In Render, choose **New → Blueprint**, connect the intended repository and branch, and review `render.yaml`.
3. If keeping ₹0, accept that the service is a test/demo and that continuous collection and durable storage are not guaranteed. If durable 24/7 collection is a hard requirement, a paid worker and persistent storage are required.
4. Add `ALERT_WEBHOOK_URL` only through Render's Environment dashboard; never commit it.
5. After deploy, check `/healthz`, `/readyz`, and `/status`; verify a restart and stale-data alert. Use an independent monitor against `/readyz`.
6. Confirm the public Delta socket is reachable from Render's region. If the service cannot connect, keep the status unready and do not fill gaps with fabricated data.

## Safety boundary

This service subscribes to public market-data channels through the existing read-only collector. It does not use account credentials, private endpoints, order submission, cancellation, or position modification. Never add exchange secrets to this service.


## Backup/recovery drill

The repository includes `maintenance/render_data_backup.py`. It creates a SHA-256-manifested tar.gz snapshot, verifies every member before restore, rejects unsafe paths and symlinks, and refuses overwrites by default.

Example on a host with data:
```sh
python maintenance/render_data_backup.py create --source data --output /path/on/durable-storage/delta-data-backup.tar.gz
python maintenance/render_data_backup.py verify /path/on/durable-storage/delta-data-backup.tar.gz
python maintenance/render_data_backup.py restore /path/on/durable-storage/delta-data-backup.tar.gz --destination /tmp/delta-restore-test
```

The included tests exercise round-trip restore, overwrite protection, checksum failure, and symlink rejection. This is a **local archive tool**, not off-host backup delivery. For real disaster recovery, the output path must be outside the Render instance (for example, a separately configured storage service); no remote backup destination is configured by this change. A backup written to Render Free's own filesystem disappears with that instance.
