"""SQLite registry for reproducible, isolated trading research."""

from pathlib import Path
import sqlite3

SCHEMA_VERSION = 1

_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS research_hypotheses (
    hypothesis_id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    evidence_status TEXT NOT NULL DEFAULT 'hypothesis'
        CHECK (evidence_status IN ('hypothesis','preliminary_result',
                                   'validated_result','insufficient_evidence')),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_datasets (
    dataset_version TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    source_path TEXT NOT NULL,
    byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
    record_count INTEGER,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    sampling_method TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_features (
    feature_name TEXT NOT NULL,
    version TEXT NOT NULL,
    definition TEXT NOT NULL,
    formula TEXT NOT NULL,
    source_event TEXT NOT NULL,
    window TEXT NOT NULL,
    normalization TEXT NOT NULL,
    timestamp_semantics TEXT NOT NULL,
    lookahead_safe INTEGER NOT NULL CHECK (lookahead_safe IN (0,1)),
    created_at TEXT NOT NULL,
    PRIMARY KEY (feature_name, version)
);
CREATE TABLE IF NOT EXISTS research_experiments (
    experiment_id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL REFERENCES research_hypotheses(hypothesis_id),
    dataset_version TEXT NOT NULL REFERENCES research_datasets(dataset_version),
    feature_name TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    prediction_horizon TEXT NOT NULL,
    sampling_method TEXT NOT NULL,
    feature_parameters TEXT NOT NULL,
    model TEXT NOT NULL,
    training_period TEXT NOT NULL,
    validation_period TEXT NOT NULL,
    test_period TEXT NOT NULL,
    transaction_cost_assumption TEXT NOT NULL,
    slippage_assumption TEXT NOT NULL,
    latency_assumption TEXT NOT NULL,
    metrics TEXT NOT NULL DEFAULT '{}',
    statistical_tests TEXT NOT NULL DEFAULT '{}',
    result TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned','running','completed','failed',
                          'insufficient_evidence','validated')),
    code_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (feature_name, feature_version)
        REFERENCES research_features(feature_name, version)
);
CREATE INDEX IF NOT EXISTS idx_experiments_hypothesis
    ON research_experiments(hypothesis_id, created_at);
CREATE INDEX IF NOT EXISTS idx_experiments_dataset
    ON research_experiments(dataset_version);
"""
def initialize_database(path: str | Path) -> None:
    """Create the isolated research registry; existing rows are preserved."""
    database = Path(path)
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.executescript(_SCHEMA)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS research_meta "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT OR IGNORE INTO research_meta(key, value) VALUES (?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )
