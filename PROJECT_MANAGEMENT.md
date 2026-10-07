# BTC Fisher Trader — Project Management Checkpoint

## Current execution policy
- Research and paper trading are enabled.
- Real exchange order submission is disabled.
- Promotion requires the evidence gate plus explicit human authorization.
- Frozen MonthlyFisher production parameters remain unchanged.

## Active paper systems
- ABSREV live execution baseline
- Scalper Portfolio V1: 12 strategy families + execution router
- Live paper analytics / leaderboard
- Delta microstructure collector

## Backup policy
Git tracks source code, tests, configuration templates, safety policy and documentation.
Generated market streams, logs, runtime state and private credentials are excluded.

## Validation
Core trading safety, risk, paper lifecycle, persistence and signal-pipeline tests must pass before promotion.
External exchange smoke tests are opt-in and must not run during normal test collection.

## Promotion
A strategy remains blocked until sufficient completed paper trades, positive net expectancy,
profit factor, win rate and realistic execution evidence are available.
