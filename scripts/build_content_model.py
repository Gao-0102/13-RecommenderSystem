"""Build the deterministic genre-vector artifact used by the business content provider."""
import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "data/packages/rec-course-v3-train5-1.0.0"
OUTPUT = ROOT / "models/business/content-genre-v1"
MODEL_VERSION = "content-genre-v1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    movies_path = PACKAGE / "movies.csv"
    catalog_path = PACKAGE / "training-catalog.csv"
    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    catalog = {row["movie_id"] for row in csv.DictReader(catalog_path.open(encoding="utf-8", newline=""))}
    rows = [row for row in csv.DictReader(movies_path.open(encoding="utf-8", newline="")) if row["movie_id"] in catalog]
    genres = sorted({genre for row in rows for genre in row["genres"].split("|") if genre and genre != "(no genres listed)"})
    positions = {genre: index for index, genre in enumerate(genres)}
    vectors = {}
    for row in rows:
        vector = [0] * len(genres)
        for genre in row["genres"].split("|"):
            if genre in positions:
                vector[positions[genre]] = 1
        vectors[row["movie_id"]] = vector
    OUTPUT.mkdir(parents=True, exist_ok=True)
    artifact = OUTPUT / "content_model.json"
    artifact.write_text(json.dumps({"model_version": MODEL_VERSION, "genres": genres, "movie_vectors": vectors},
                                   ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    sidecar = {
        "algorithm": "content", "model_version": MODEL_VERSION, "runtime_mode": "business",
        "dataset_version": "rec-course-v3-train5-1.0.0", "split_version": "temporal-v1-cold500-train5-v3",
        "schema_version": "student-eight-v3",
        "manifest_sha256": "fcfb9a195a56709773696aab02f769c691778af0eb433a1e0778a71c4b289b9e",
        "training_files": {"business/history_ratings.csv": manifest["files"]["business/history_ratings.csv"]["sha256"]},
        "feature_files": {name: manifest["files"][name]["sha256"] for name in ["movies.csv", "training-catalog.csv"]},
        "artifacts": {"content_model.json": digest(artifact)},
        "parameters": {"features": "genres one-hot", "positive_rating_threshold": 4.0,
                       "profile_weight": "rating - 3.0", "ranking": "cosine similarity"},
        "tool_versions": {"python": "stdlib"},
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT / "manifest.json")


if __name__ == "__main__":
    main()
