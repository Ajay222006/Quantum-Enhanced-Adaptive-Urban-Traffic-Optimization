import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.prediction.traffic_prediction import TrafficPredictionTrainer


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train XGBoost traffic-state predictors")
    parser.add_argument("--data", required=True, help="CSV created by collect_traffic_dataset.py")
    parser.add_argument("--model", default="models/traffic_predictor.joblib")
    parser.add_argument("--interval", type=int, default=5)
    parser.add_argument("--history", type=int, default=30)
    parser.add_argument("--horizon", type=int, default=30)
    args = parser.parse_args()

    result = TrafficPredictionTrainer().train(
        args.data,
        args.model,
        interval_seconds=args.interval,
        history_seconds=args.history,
        horizon_seconds=args.horizon,
    )
    print(json.dumps(result, indent=2))
