# Edge Node Quality Loop

## What it does

`maintenance/edge_node_healthcheck.sh` runs a small, targeted pytest gate for the new risk oracle, watchdog policy, hedge coordinator, adaptive pacing, live execution locks and storage journal. Passing checks exit without calling an AI model. On a failure, the script invokes the authenticated Codex CLI in read-only mode and saves a diagnosis to `logs/edge_node_ai_diagnosis.md`.

This is intentionally a **detect → diagnose → review → patch → test** loop. It does not silently let an AI agent edit live trading/risk code, enable live execution, or submit/cancel orders. A human reviews and applies the patch; the tests then verify it. This preserves the existing uncommitted repository changes and prevents an unreviewed model edit from changing capital-risk behavior.

## Run once

```sh
cd ~/btc_fisher_trader
./maintenance/edge_node_healthcheck.sh
tail -80 logs/edge_node_healthcheck.log
```

## Schedule hourly on Android

Requires the Termux:API app and the `termux-api` package. Android JobScheduler may delay jobs due to Doze, battery saver or OS scheduling; this is not a hard real-time supervisor.

```sh
termux-job-scheduler --job-id 6210 \
  --script "$HOME/btc_fisher_trader/maintenance/edge_node_healthcheck.sh" \
  --period-ms 3600000 \
  --battery-not-low true \
  --storage-not-low true \
  --persisted true
```

Inspect/cancel the job:

```sh
termux-job-scheduler --pending
termux-job-scheduler --cancel 6210
```

## AI provider status

Codex CLI is installed and authenticated on the current Termux node. Gemini CLI currently exits with an Android/Termux compatibility guard in its installed runtime; it is not used by this scheduled loop. The `GEMINI_API_KEY` variable is present but its value must never be logged or printed. An API fallback can be added separately if quota and billing constraints are confirmed.

## Limitations

- The job scheduler is not an independent server and cannot guarantee hourly execution while Android suspends or kills Termux.
- It checks code quality, not exchange connectivity or actual order safety.
- The watchdog and hedge modules are policy cores only; they are not wired to authenticated exchange cancellation.
- A passing test suite does not prove a profitable edge.
