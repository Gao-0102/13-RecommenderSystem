import csv
import hashlib
import heapq
import json
import sys
from collections import defaultdict
from math import sqrt
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "data/packages/rec-course-v3-train5-1.0.0"
OUTPUT = ROOT / "models/business/itemcf-v1"
MODEL_VERSION = "itemcf-v1"
POSITIVE_RATING_THRESHOLD = 4.0
MIN_COOCCURRENCE = 3
NEIGHBOR_SIZE = 50


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verified_rows(path: Path, expected: dict):
    if not path.is_file() or path.stat().st_size != expected["bytes"] or sha256(path) != expected["sha256"]:
        raise ValueError(f"冻结文件摘要或大小不符: {path}")
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != expected["columns"]:
            raise ValueError(f"CSV字段不符: {path}")
        rows = list(reader)
    if len(rows) != expected["records"]:
        raise ValueError(f"CSV行数不符: {path}")
    return rows


def main() -> None:
    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    catalog_rows = verified_rows(PACKAGE / "training-catalog.csv", manifest["files"]["training-catalog.csv"])
    rating_rows = verified_rows(PACKAGE / "business/history_ratings.csv", manifest["files"]["business/history_ratings.csv"])
    catalog = {row["movie_id"] for row in catalog_rows}

    user_items = defaultdict(list)
    positive_ratings = 0
    for row in rating_rows:
        movie_id = row["movieId"]
        rating = float(row["rating"])
        if movie_id in catalog and rating >= POSITIVE_RATING_THRESHOLD:
            user_items[row["userId"]].append(int(movie_id))
            positive_ratings += 1
    for items in user_items.values():
        items.sort()

    item_users = defaultdict(list)
    for items in user_items.values():
        for movie_id in items:
            item_users[movie_id].append(items)

    popularity = {movie_id: len(users) for movie_id, users in item_users.items()}
    all_items = sorted(popularity)
    lower_heaps = {movie_id: [] for movie_id in all_items}
    item_neighbors = {}

    for source_id in all_items:
        cooccurrence = defaultdict(int)
        for items in item_users[source_id]:
            for target_id in items:
                if target_id > source_id:
                    cooccurrence[target_id] += 1

        higher_heap = []
        source_norm = sqrt(popularity[source_id])
        for target_id, support in cooccurrence.items():
            if support < MIN_COOCCURRENCE:
                continue
            raw_similarity = support / (source_norm * sqrt(popularity[target_id]))
            similarity = round(raw_similarity, 9)
            candidate = (similarity, -target_id, support)
            if len(higher_heap) < NEIGHBOR_SIZE:
                heapq.heappush(higher_heap, candidate)
            elif candidate[:2] > higher_heap[0][:2]:
                heapq.heapreplace(higher_heap, candidate)

            lower_candidate = (similarity, -source_id, support)
            target_heap = lower_heaps[target_id]
            if len(target_heap) < NEIGHBOR_SIZE:
                heapq.heappush(target_heap, lower_candidate)
            elif lower_candidate[:2] > target_heap[0][:2]:
                heapq.heapreplace(target_heap, lower_candidate)

        neighbors = sorted(lower_heaps[source_id] + higher_heap, key=lambda item: (-item[0], -item[1]))[:NEIGHBOR_SIZE]
        item_neighbors[str(source_id)] = [
            {
                "movie_id": str(-neighbor_id),
                "similarity": round(similarity, 9),
                "cooccurrence": support,
            }
            for similarity, neighbor_id, support in neighbors
        ]
        del lower_heaps[source_id]
        del item_users[source_id]

    OUTPUT.mkdir(parents=True, exist_ok=True)
    artifact_path = OUTPUT / "itemcf_model.json"
    artifact = {
        "model_version": MODEL_VERSION,
        "algorithm": "itemcf",
        "parameters": {
            "positive_rating_threshold": POSITIVE_RATING_THRESHOLD,
            "min_cooccurrence": MIN_COOCCURRENCE,
            "neighbor_size": NEIGHBOR_SIZE,
            "similarity": "positive interaction cosine: cooccurrence / sqrt(item_user_count_i * item_user_count_j)",
            "ranking_score": "sum(similarity * (rating - 3.0))",
        },
        "item_count": len(item_neighbors),
        "positive_rating_count": positive_ratings,
        "positive_user_count": len(user_items),
        "item_neighbors": item_neighbors,
    }
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    sidecar = {
        "algorithm": "itemcf",
        "model_version": MODEL_VERSION,
        "runtime_mode": "business",
        "dataset_version": manifest["dataset_version"],
        "split_version": manifest["split_version"],
        "schema_version": manifest["schema_version"],
        "manifest_sha256": "fcfb9a195a56709773696aab02f769c691778af0eb433a1e0778a71c4b289b9e",
        "training_files": {
            "business/history_ratings.csv": manifest["files"]["business/history_ratings.csv"]["sha256"]
        },
        "feature_files": {
            "training-catalog.csv": manifest["files"]["training-catalog.csv"]["sha256"]
        },
        "artifacts": {
            "itemcf_model.json": sha256(artifact_path)
        },
        "parameters": artifact["parameters"],
        "tool_versions": {
            "python": ".".join(str(part) for part in sys.version_info[:3])
        },
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT / "manifest.json")


if __name__ == "__main__":
    main()
