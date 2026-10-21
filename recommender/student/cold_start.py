"""Cold-start router provider for the business API."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from math import sqrt
from pathlib import Path

from recommender.business import read_history
from recommender.contracts import Algorithm, RecommendationItem, RecommendationRequest, RecommendationResult
from recommender.data import DATASET, SPLIT, require


MODEL_VERSION = "cold-start-v1"
CONTENT_MODEL_VERSION = "content-genre-v1"


@dataclass
class ColdStartProvider:
    model_manifest_path: Path

    def __post_init__(self):
        artifact_path = self.model_manifest_path.parent / "cold_start_model.json"
        try:
            raw = json.loads(artifact_path.read_text(encoding="utf-8"))
            self._popular_top50 = raw["popular_top50"]
            self._popular_source = raw.get("popular_source_version", "popular-v1")
            params = raw.get("parameters", {})
            self._positive_threshold = float(params.get("positive_rating_threshold", 4.0))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("冷启动模型工件无法读取") from exc
        require(raw.get("model_version") == MODEL_VERSION and self._popular_top50,
                "冷启动模型工件版本或内容非法", "MODEL_BINDING_INVALID")

        content_dir = Path("models/business/content-genre-v1")
        content_artifact = content_dir / "content_model.json"
        try:
            content_raw = json.loads(content_artifact.read_text(encoding="utf-8"))
            self._genres = tuple(content_raw["genres"])
            self._content_vectors = {
                str(movie_id): tuple(float(v) for v in vector)
                for movie_id, vector in content_raw["movie_vectors"].items()
            }
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("内容模型工件无法读取") from exc
        require(content_raw.get("model_version") == CONTENT_MODEL_VERSION,
                "内容模型工件版本非法", "MODEL_BINDING_INVALID")

    def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        require(request.runtime_mode == "business", "冷启动模型只能用于业务模式", "DATA_MODE_INVALID")
        history = read_history(request)
        rated_ids = {feedback.movie_id for feedback in history.ratings}
        positive_count = sum(1 for f in history.ratings if float(f.rating) >= self._positive_threshold)

        if positive_count == 0:
            items = self._popular_branch(rated_ids, request.limit)
            source = "cold_start:popular"
        else:
            items = self._content_branch(rated_ids, history, request.limit)
            source = "cold_start:content"

        for item in items:
            item.recall_sources = [source]

        return RecommendationResult(
            algorithm=Algorithm.cold_start,
            model_version=MODEL_VERSION,
            dataset_version=DATASET,
            split_version=SPLIT,
            runtime_mode="business",
            generated_at=datetime.now(timezone.utc),
            items=items,
        )

    def _popular_branch(self, rated_ids: set[str], limit: int) -> list[RecommendationItem]:
        items: list[RecommendationItem] = []
        for entry in self._popular_top50:
            movie_id = str(entry["movie_id"])
            if movie_id in rated_ids:
                continue
            items.append(RecommendationItem(
                movie_id=movie_id,
                rank=len(items) + 1,
                algorithm=Algorithm.cold_start,
                model_version=MODEL_VERSION,
                score=float(entry.get("normalized_score", 0.0)),
            ))
            if len(items) >= limit:
                break
        return items

    def _content_branch(self, rated_ids: set[str], history, limit: int) -> list[RecommendationItem]:
        rated = {feedback.movie_id: float(feedback.rating) for feedback in history.ratings}
        profile = [0.0] * len(self._genres)
        total_weight = 0.0
        for movie_id, rating in rated.items():
            if rating < self._positive_threshold or movie_id not in self._content_vectors:
                continue
            weight = rating - 3.0
            for idx, value in enumerate(self._content_vectors[movie_id]):
                profile[idx] += weight * value
            total_weight += weight

        profile_norm = sqrt(sum(value * value for value in profile))
        candidates: list[tuple[float, str]] = []
        if total_weight and profile_norm:
            for movie_id, vector in self._content_vectors.items():
                if movie_id in rated_ids:
                    continue
                norm = sqrt(sum(value * value for value in vector))
                if not norm:
                    continue
                score = sum(left * right for left, right in zip(profile, vector)) / (profile_norm * norm)
                if score > 0:
                    candidates.append((score, movie_id))
        candidates.sort(key=lambda v: (-v[0], int(v[1])))
        return [
            RecommendationItem(
                movie_id=movie_id,
                rank=index,
                algorithm=Algorithm.cold_start,
                model_version=MODEL_VERSION,
                score=score,
            )
            for index, (score, movie_id) in enumerate(candidates[:limit], 1)
        ]
