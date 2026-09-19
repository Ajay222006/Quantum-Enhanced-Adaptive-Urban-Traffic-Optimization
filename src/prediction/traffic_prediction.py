"""Traffic-state collection, XGBoost training, and real-time prediction."""

from __future__ import annotations

import csv
import json
import os
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Deque, Dict, Iterable, List, Mapping, Sequence, Tuple

import joblib
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.multioutput import MultiOutputRegressor
from xgboost import XGBRegressor

FEATURE_NAMES = ("density", "queue", "avg_speed", "flow", "capacity", "phase")
TARGET_NAMES = ("density", "queue", "flow")


def _numeric_signal_phase(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _numeric(record: Mapping, name: str) -> float:
    try:
        return float(record.get(name, 0.0))
    except (TypeError, ValueError):
        return 0.0


def state_to_rows(state: Mapping, timestamp: float, scenario: str = "unknown") -> List[dict]:
    """Flatten estimator output into one row per intersection approach."""
    rows = []
    for intersection_id, directions in state.items():
        for direction, values in directions.items():
            rows.append({
                "timestamp": float(timestamp),
                "scenario": scenario,
                "intersection_id": intersection_id,
                "direction": direction,
                "density": _numeric(values, "density"),
                "queue": _numeric(values, "queue"),
                "avg_speed": _numeric(values, "avg_speed"),
                "flow": _numeric(values, "flow"),
                "capacity": _numeric(values, "capacity"),
                "phase": _numeric_signal_phase(values.get("phase", 0)),
            })
    return rows


class TrafficStateRecorder:
    """Persist periodic SUMO estimator snapshots as a CSV time series."""

    COLUMNS = ["timestamp", "scenario", "intersection_id", "direction", *FEATURE_NAMES]

    def __init__(self, output_path: str):
        self.output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(self.output_path) or ".", exist_ok=True)
        self.rows: List[dict] = []

    def record(self, state: Mapping, timestamp: float, scenario: str = "unknown") -> List[dict]:
        rows = state_to_rows(state, timestamp, scenario)
        self.rows.extend(rows)
        return rows

    def save(self) -> str:
        with open(self.output_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.COLUMNS)
            writer.writeheader()
            writer.writerows(self.rows)
        return self.output_path


class TrafficStateDataset:
    """Create lagged inputs and future targets from recorder CSV data."""

    def __init__(self, interval_seconds: int = 5, history_seconds: int = 30, horizon_seconds: int = 30):
        if interval_seconds <= 0 or history_seconds < interval_seconds or horizon_seconds <= 0:
            raise ValueError("interval_seconds, history_seconds, and horizon_seconds must be positive and ordered")
        self.interval_seconds = interval_seconds
        self.history_steps = history_seconds // interval_seconds
        self.horizon_steps = horizon_seconds // interval_seconds
        if self.history_steps < 1:
            raise ValueError("history_seconds must be at least interval_seconds")

    def _load(self, csv_path: str) -> Dict[Tuple[str, str, str], List[dict]]:
        groups = defaultdict(list)
        with open(csv_path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                for name in FEATURE_NAMES:
                    row[name] = float(row[name])
                row["timestamp"] = float(row["timestamp"])
                key = (str(row.get("scenario", "unknown")), str(row["intersection_id"]), str(row["direction"]))
                groups[key].append(row)
        for rows in groups.values():
            rows.sort(key=lambda item: item["timestamp"])
        return groups

    def build(self, csv_path: str):
        """Return X, y, and approach keys in chronological sample order."""
        groups = self._load(csv_path)
        X, y, keys, timestamps = [], [], [], []
        for key, rows in groups.items():
            for target_index in range(self.history_steps - 1, len(rows) - self.horizon_steps):
                history = rows[target_index - self.history_steps + 1:target_index + 1]
                future = rows[target_index + self.horizon_steps]
                features = []
                for item in history:
                    features.extend(item[name] for name in FEATURE_NAMES)
                X.append(features)
                y.append([future[name] for name in TARGET_NAMES])
                keys.append(key)
                timestamps.append(rows[target_index]["timestamp"])
        if not X:
            raise ValueError("Not enough time-series data for the requested history and prediction horizon")
        return np.asarray(X, dtype=float), np.asarray(y, dtype=float), keys, timestamps


class TrafficPredictionTrainer:
    """Train one multi-output XGBoost model per intersection approach."""

    def __init__(self, random_state: int = 42):
        self.random_state = random_state

    def train(self, csv_path: str, model_path: str, interval_seconds: int = 5,
              history_seconds: int = 30, horizon_seconds: int = 30) -> dict:
        dataset = TrafficStateDataset(interval_seconds, history_seconds, horizon_seconds)
        X, y, keys, timestamps = dataset.build(csv_path)
        order = np.argsort(np.asarray(timestamps))
        X, y = X[order], y[order]
        keys = [keys[index] for index in order]

        n = len(X)
        train_end = max(1, int(n * 0.70))
        validation_end = max(train_end + 1, int(n * 0.85))
        validation_end = min(validation_end, n)
        if train_end >= validation_end or validation_end >= n:
            raise ValueError("Need enough samples for chronological train/validation/test splits")

        models = {}
        metrics = {}
        candidate_params = [
            {"max_depth": 3, "learning_rate": 0.05},
            {"max_depth": 4, "learning_rate": 0.05},
            {"max_depth": 4, "learning_rate": 0.08},
        ]

        for key in sorted(set(keys)):
            key_mask = np.asarray([item == key for item in keys])
            key_X, key_y = X[key_mask], y[key_mask]
            key_n = len(key_X)
            if key_n < 5:
                continue
            key_train_end = max(1, int(key_n * 0.70))
            key_validation_end = max(key_train_end + 1, int(key_n * 0.85))
            key_test_end = key_n
            if key_validation_end >= key_test_end:
                continue

            best_params = None
            best_val_rmse = float("inf")
            for params in candidate_params:
                model = MultiOutputRegressor(XGBRegressor(
                    n_estimators=150,
                    max_depth=params["max_depth"],
                    learning_rate=params["learning_rate"],
                    subsample=0.9,
                    colsample_bytree=0.9,
                    objective="reg:squarederror",
                    random_state=self.random_state,
                    n_jobs=1,
                ))
                model.fit(key_X[:key_train_end], key_y[:key_train_end])
                val_prediction = model.predict(key_X[key_train_end:key_validation_end])
                val_actual = key_y[key_train_end:key_validation_end]
                val_rmse = float(np.sqrt(mean_squared_error(val_actual, val_prediction)))
                if val_rmse < best_val_rmse:
                    best_val_rmse = val_rmse
                    best_params = params

            if best_params is None:
                continue

            model = MultiOutputRegressor(XGBRegressor(
                n_estimators=150,
                max_depth=best_params["max_depth"],
                learning_rate=best_params["learning_rate"],
                subsample=0.9,
                colsample_bytree=0.9,
                objective="reg:squarederror",
                random_state=self.random_state,
                n_jobs=1,
            ))
            train_val_X = np.concatenate([key_X[:key_train_end], key_X[key_train_end:key_validation_end]], axis=0)
            train_val_y = np.concatenate([key_y[:key_train_end], key_y[key_train_end:key_validation_end]], axis=0)
            model.fit(train_val_X, train_val_y)
            test_prediction = model.predict(key_X[key_validation_end:key_test_end])
            test_actual = key_y[key_validation_end:key_test_end]
            metrics["|".join(str(v) for v in key)] = {
                "mae": float(mean_absolute_error(test_actual, test_prediction)),
                "rmse": float(np.sqrt(mean_squared_error(test_actual, test_prediction))),
                "r2": float(r2_score(test_actual, test_prediction, multioutput="uniform_average")),
                "validation_rmse": float(best_val_rmse),
                "test_samples": int(len(test_actual)),
            }
            models[key] = model

        if not models:
            raise ValueError("No approach had enough samples for training and testing")

        artifact = {
            "models": models,
            "feature_names": FEATURE_NAMES,
            "target_names": TARGET_NAMES,
            "interval_seconds": interval_seconds,
            "history_seconds": history_seconds,
            "horizon_seconds": horizon_seconds,
            "metrics": metrics,
        }
        os.makedirs(os.path.dirname(os.path.abspath(model_path)) or ".", exist_ok=True)
        joblib.dump(artifact, model_path)
        return {
            "model_path": os.path.abspath(model_path),
            "samples": int(n),
            "approaches": len(models),
            "metrics": metrics,
        }


class RealTimeTrafficPredictor:
    """Serve predictions from recent estimator snapshots during SUMO control."""

    def __init__(self, model_path: str):
        self.artifact = joblib.load(model_path)
        self.history_steps = self.artifact["history_seconds"] // self.artifact["interval_seconds"]
        self.models = self.artifact["models"]
        self.history: Dict[Tuple[str, str], Deque[dict]] = defaultdict(lambda: deque(maxlen=self.history_steps))

    def update(self, state: Mapping, timestamp: float) -> dict:
        """Add current state and return predicted density, queue, and flow."""
        for row in state_to_rows(state, timestamp):
            key = (row["intersection_id"], row["direction"])
            self.history[key].append(row)

        predictions = defaultdict(dict)
        for key, rows in self.history.items():
            model = self.models.get(key)
            if model is None or len(rows) < self.history_steps:
                continue
            features = np.asarray([[value for row in rows for value in (row[name] for name in FEATURE_NAMES)]])
            predicted = model.predict(features)[0]
            predictions[key[0]][key[1]] = {
                "density": max(0.0, float(predicted[0])),
                "queue": max(0.0, float(predicted[1])),
                "flow": max(0.0, float(predicted[2])),
                "horizon_seconds": self.artifact["horizon_seconds"],
            }
        return dict(predictions)
