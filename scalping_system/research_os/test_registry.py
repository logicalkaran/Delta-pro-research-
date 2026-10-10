import sqlite3

from research_os.registry import initialize_database


def test_initialization_is_idempotent_and_preserves_rows(tmp_path):
    path = tmp_path / "registry.sqlite3"
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO research_hypotheses VALUES (?, ?, ?, ?)",
            ("R1", "Does OFI predict short horizon returns?", "hypothesis", "now"),
        )
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "research_hypotheses", "research_datasets", "research_features",
            "research_experiments", "research_meta",
        } <= tables
        assert connection.execute(
            "SELECT count(*) FROM research_hypotheses"
        ).fetchone()[0] == 1


def test_feature_versions_and_lookahead_flag_are_constrained(tmp_path):
    path = tmp_path / "registry.sqlite3"
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        row = ("OFI", "1", "definition", "formula", "book_update", "event",
               "none", "available_at_event_ts", 1, "now")
        connection.execute(
            "INSERT INTO research_features VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            row,
        )
        try:
            connection.execute(
                "INSERT INTO research_features VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("duplicate feature version was accepted")
        try:
            connection.execute(
                "INSERT INTO research_features VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("bad", "1", "d", "f", "event", "event", "none", "t", 2, "now"),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("invalid lookahead safety value was accepted")
