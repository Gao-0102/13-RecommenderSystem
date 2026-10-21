"""Genre-vector content recommender for the business API."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from math import sqrt
from pathlib import Path

from recommender.business import read_history
from recommender.contracts import Algorithm, RecommendationItem, RecommendationRequest, RecommendationResult
from recommender.data import DATASET, SPLIT, require


MODEL_VERSION = "content-genre-v1"


@dataclass
class ContentProvider:
    model_manifest_path: Path

    def __post_init__(self):
        artifact = self.model_manifest_path.parent / "content_model.json"
        try:
            raw = json.loads(artifact.read_text(encoding="utf-8"))
            self._genres = tuple(raw["genres"])
            self._vectors = {str(movie_id): tuple(float(value) for value in vector)
                             for movie_id, vector in raw["movie_vectors"].items()}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("内容模型工件无法读取") from exc
        require(raw.get("model_version") == MODEL_VERSION and self._genres and self._vectors,
                "内容模型工件版本或内容非法", "MODEL_BINDING_INVALID")

    def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        require(request.runtime_mode == "business", "内容业务模型不能用于评价模式", "DATA_MODE_INVALID")
        history = read_history(request)
        rated = {feedback.movie_id: float(feedback.rating) for feedback in history.ratings}
        profile = [0.0] * len(self._genres)
        total_weight = 0.0
        for movie_id, rating in rated.items():
            # Ratings below 4 are excluded: they express no positive content preference.
            if rating < 4.0 or movie_id not in self._vectors:
                continue
            weight = rating - 3.0
            for index, value in enumerate(self._vectors[movie_id]):
                profile[index] += weight * value
            total_weight += weight

        profile_norm = sqrt(sum(value * value for value in profile))
        candidates: list[tuple[float, str]] = []
        if total_weight and profile_norm:
            for movie_id, vector in self._vectors.items():
                if movie_id in rated:
                    continue
                norm = sqrt(sum(value * value for value in vector))
                if not norm:
                    continue
                score = sum(left * right for left, right in zip(profile, vector)) / (profile_norm * norm)
                if score > 0:
                    candidates.append((score, movie_id))
        candidates.sort(key=lambda value: (-value[0], int(value[1])))
        items = [RecommendationItem(movie_id=movie_id, rank=index, algorithm=Algorithm.content,
                                    model_version=MODEL_VERSION, score=score)
                 for index, (score, movie_id) in enumerate(candidates[:request.limit], 1)]
        return RecommendationResult(algorithm=Algorithm.content, model_version=MODEL_VERSION,
                                    dataset_version=DATASET, split_version=SPLIT, runtime_mode="business",
                                    generated_at=datetime.now(timezone.utc), items=items)
