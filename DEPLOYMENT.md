# DeltaPro deployment and monitoring

## Container deployment
Build the repository's Dockerfile and run the container with port 3000 exposed. Configure the hosting platform's health check to use `/api/btc-engine/health` only if that endpoint's dependency semantics match your desired readiness check; otherwise use `/api/delta/tickers` as a live-upstream check. Set secrets only in the hosting provider's secret manager. Do not put API keys in Vite client variables.

## Scheduled market-data validation
GitHub Actions workflow `.github/workflows/market-data-monitor.yml` runs on pushes, manually, and hourly at minute 17 UTC. It installs the lockfile, type-checks, validates indicator research, builds the app, starts the API, and checks public Delta market data. GitHub Actions is a periodic CI monitor, not a continuously running trading process or a guarantee of alert delivery.

## Important limitations
The scheduled job uses GitHub-hosted runners and may be delayed by platform scheduling. It does not submit orders, modify strategies, or persist exchange history. Configure repository Actions notifications for failed runs. Production hosting requires a hosting account and provider-specific deployment setup; no provider credentials are committed.
