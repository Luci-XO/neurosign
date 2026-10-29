import gzip
import json
import sqlite3
import unittest

import numpy as np

from analysis.movement_features import (
    MovementAnalysisError,
    extract_movement_features,
)
from analysis.assessment import build_summary
from analysis.scoring import movement_stage_score
from db import _ensure_movement_columns


class MovementGuideDeviationTests(unittest.TestCase):
    def samples_for(self, task_type, offset_x=0.0, offset_y=0.0):
        timestamps = np.arange(500) * 10
        if task_type == "spiral":
            angle = np.linspace(0, 8 * np.pi, len(timestamps))
            radius = (angle / (8 * np.pi)) * 180
            x = 300 + radius * np.cos(angle)
            y = 200 + radius * np.sin(angle)
        else:
            x = np.linspace(40, 560, len(timestamps))
            y = 200 + 100 * np.sin(((x - 40) / 520) * 4 * np.pi)
        return [
            [float(t), float(px + offset_x), float(py + offset_y)]
            for t, px, py in zip(timestamps, x, y)
        ]

    def test_on_guide_trace_has_small_deviation(self):
        for task_type in ("spiral", "wave"):
            with self.subTest(task_type=task_type):
                features = extract_movement_features(self.samples_for(task_type), task_type)
                self.assertLess(features["guide_deviation"], 3.0)

    def test_shifted_trace_has_large_deviation_and_score(self):
        features = extract_movement_features(
            self.samples_for("wave", offset_y=40), "wave"
        )
        self.assertGreater(features["guide_deviation"], 30.0)
        self.assertGreaterEqual(movement_stage_score(features), 50.0)

    def test_small_guide_deviation_does_not_raise_score(self):
        self.assertEqual(
            movement_stage_score({"tremor_share": 0.22, "guide_deviation": 8.0}),
            0.0,
        )

    def test_free_shape_has_no_guide_deviation(self):
        features = extract_movement_features(self.samples_for("free"), "free")
        self.assertIsNone(features["guide_deviation"])
        self.assertEqual(movement_stage_score(features), 0.0)

    def test_invalid_canvas_and_task_are_rejected(self):
        samples = self.samples_for("wave")
        with self.assertRaises(MovementAnalysisError):
            extract_movement_features(samples, "wave", (50, 400))
        with self.assertRaises(MovementAnalysisError):
            extract_movement_features(samples, "unknown")

    def test_database_migration_preserves_existing_path_deviation(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                "CREATE TABLE movement_results (id INTEGER PRIMARY KEY, path_deviation REAL)"
            )
            conn.execute(
                "INSERT INTO movement_results (id, path_deviation) VALUES (1, 2.5)"
            )
            _ensure_movement_columns(conn)
            _ensure_movement_columns(conn)
            row = conn.execute("SELECT * FROM movement_results WHERE id=1").fetchone()
            self.assertEqual(row["path_deviation"], 2.5)
            self.assertIsNone(row["guide_deviation"])
        finally:
            conn.close()

    def test_summary_does_not_average_down_one_high_movement_score(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript(
                """
                CREATE TABLE users (id INTEGER, name TEXT, age INTEGER, gender TEXT);
                CREATE TABLE sessions (
                    id INTEGER, user_id INTEGER, device TEXT, created_at TEXT,
                    completed_at TEXT, verdict_code TEXT
                );
                CREATE TABLE voice_results (
                    session_id INTEGER, step INTEGER, stage_score REAL, change_index REAL
                );
                CREATE TABLE movement_results (
                    id INTEGER PRIMARY KEY, session_id INTEGER, step INTEGER,
                    task_type TEXT, stage_score REAL, change_index REAL,
                    guide_deviation REAL
                );
                CREATE TABLE raw_signals (
                    movement_result_id INTEGER, data_gz BLOB
                );
                INSERT INTO users VALUES (1, 'Test', 60, 'prefer_not_to_say');
                INSERT INTO sessions VALUES (1, 1, 'mouse', '', '', NULL);
                INSERT INTO movement_results VALUES (5, 1, 5, 'spiral', 0, NULL, NULL);
                INSERT INTO movement_results VALUES (8, 1, 8, 'spiral', 80, 0, NULL);
                """
            )
            samples = self.samples_for("spiral", offset_x=80)
            conn.execute(
                "INSERT INTO raw_signals VALUES (?, ?)",
                (5, gzip.compress(json.dumps(samples).encode("utf-8"))),
            )
            summary = build_summary(conn, 1)
            movement_flag = next(
                flag for flag in summary["verdict"]["flags"] if flag["key"] == "move_level"
            )
            self.assertEqual(movement_flag["value"], 100.0)
            self.assertTrue(movement_flag["flagged"])
            refreshed = conn.execute(
                "SELECT guide_deviation FROM movement_results WHERE id=5"
            ).fetchone()
            self.assertGreater(refreshed["guide_deviation"], 50.0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
