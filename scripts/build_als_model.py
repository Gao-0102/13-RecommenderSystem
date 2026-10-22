import csv
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "data/packages/rec-course-v3-train5-1.0.0"
OUTPUT = ROOT / "models/business/als-v1"
MODEL_VERSION = "als-v1"

ALS_RANK = 10
ALS_REG_PARAM = 0.1
ALS_MAX_ITER = 15
ALS_SEED = 42


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))

    train_csv = PACKAGE / "business/history_ratings.csv"
    catalog_csv = PACKAGE / "training-catalog.csv"

    catalog_ids = set()
    with catalog_csv.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            catalog_ids.add(int(row["movie_id"]))

    print(f"catalog movies: {len(catalog_ids)}")

    train_rows = []
    with train_csv.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            uid = int(row["userId"])
            mid = int(row["movieId"])
            rating = float(row["rating"])
            if mid in catalog_ids:
                train_rows.append((uid, mid, rating))

    print(f"train rows (catalog-filtered): {len(train_rows)}")

    all_users = sorted({r[0] for r in train_rows})
    all_items = sorted({r[1] for r in train_rows})
    user_to_idx = {u: i for i, u in enumerate(all_users)}
    item_to_idx = {m: i for i, m in enumerate(all_items)}
    n_users = len(all_users)
    n_items = len(all_items)
    rank = ALS_RANK
    reg = ALS_REG_PARAM

    print(f"users: {n_users}, items: {n_items}, rank={rank}, reg={reg}, maxIter={ALS_MAX_ITER}")

    rng = np.random.default_rng(ALS_SEED)
    U = rng.normal(scale=0.1, size=(n_users, rank)).astype(np.float64)
    V = rng.normal(scale=0.1, size=(n_items, rank)).astype(np.float64)

    user_ratings = [[] for _ in range(n_users)]
    item_ratings = [[] for _ in range(n_items)]
    for uid, mid, rating in train_rows:
        ui = user_to_idx[uid]
        ii = item_to_idx[mid]
        user_ratings[ui].append((ii, rating))
        item_ratings[ii].append((ui, rating))

    I_reg = reg * np.eye(rank)

    t0 = time.time()
    for iteration in range(1, ALS_MAX_ITER + 1):
        for ii in range(n_items):
            ratings = item_ratings[ii]
            if not ratings:
                continue
            rows = len(ratings)
            Q = np.empty((rows, rank))
            r_vec = np.empty(rows)
            for k, (ui, rating) in enumerate(ratings):
                Q[k] = U[ui]
                r_vec[k] = rating
            A = Q.T @ Q + I_reg
            b = Q.T @ r_vec
            V[ii] = np.linalg.solve(A, b)

        for ui in range(n_users):
            ratings = user_ratings[ui]
            if not ratings:
                continue
            rows = len(ratings)
            Q = np.empty((rows, rank))
            r_vec = np.empty(rows)
            for k, (ii, rating) in enumerate(ratings):
                Q[k] = V[ii]
                r_vec[k] = rating
            A = Q.T @ Q + I_reg
            b = Q.T @ r_vec
            U[ui] = np.linalg.solve(A, b)

        total_loss = 0.0
        count = 0
        for uid, mid, rating in train_rows:
            ui = user_to_idx[uid]
            ii = item_to_idx[mid]
            pred = float(U[ui] @ V[ii])
            total_loss += (pred - rating) ** 2
            count += 1
        rmse = np.sqrt(total_loss / count)
        elapsed = time.time() - t0
        print(f"  iter {iteration:2d}: RMSE={rmse:.5f}  ({elapsed:.1f}s)")

    print(f"Training done in {time.time() - t0:.1f}s")

    item_factors = {}
    for mid, ii in item_to_idx.items():
        item_factors[str(mid)] = [round(float(v), 9) for v in V[ii]]

    user_factors = {}
    for uid, ui in user_to_idx.items():
        user_factors[str(uid)] = [round(float(v), 9) for v in U[ui]]

    OUTPUT.mkdir(parents=True, exist_ok=True)

    artifact = {
        "model_version": MODEL_VERSION,
        "algorithm": "als",
        "parameters": {
            "rank": ALS_RANK,
            "regParam": ALS_REG_PARAM,
            "maxIter": ALS_MAX_ITER,
            "optimizer": "als (numpy)",
            "seed": ALS_SEED,
            "nonnegative": False,
            "implicitPrefs": False,
        },
        "item_count": len(item_factors),
        "user_count": len(user_factors),
        "train_rows": len(train_rows),
        "item_factors": item_factors,
        "user_factors": user_factors,
    }

    artifact_path = OUTPUT / "als_model.json"
    artifact_path.write_text(
        json.dumps(artifact, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    sidecar = {
        "algorithm": "als",
        "model_version": MODEL_VERSION,
        "runtime_mode": "business",
        "dataset_version": manifest["dataset_version"],
        "split_version": manifest["split_version"],
        "schema_version": manifest["schema_version"],
        "manifest_sha256": sha256(PACKAGE / "manifest.json"),
        "training_files": {
            "business/history_ratings.csv": manifest["files"]["business/history_ratings.csv"]["sha256"],
        },
        "artifacts": {
            "als_model.json": sha256(artifact_path),
        },
        "parameters": artifact["parameters"],
        "tool_versions": {
            "python": ".".join(str(part) for part in sys.version_info[:3]),
            "numpy": np.__version__,
        },
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"\nDone! Artifacts in: {OUTPUT}")
    print(f"  als_model.json: {artifact_path.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()
