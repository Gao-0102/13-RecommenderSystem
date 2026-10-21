from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from recommender.business import read_history
from recommender.contracts import Algorithm, RecommendationItem, RecommendationRequest, RecommendationResult
from recommender.data import DATASET, SPLIT, require


MODEL_VERSION = "popular-v1"


@dataclass
class PopularProvider:
    model_manifest_path: Path

    def __post_init__(self):
        artifact = self.model_manifest_path.parent / "popular_model.json"
        try:
            raw = json.loads(artifact.read_text(encoding="utf-8"))
            self._top50 = [str(item["movie_id"]) for item in raw["bayesian_top50"]]
            self._scores = {str(item["movie_id"]): float(item["normalized_score"])
                            for item in raw["bayesian_top50"]}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("popular artifact cannot be read") from exc
        require(raw.get("model_version") == MODEL_VERSION and self._top50,
                "popular artifact version invalid or empty", "MODEL_BINDING_INVALID")

    def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        require(request.runtime_mode == "business",
                "business model cannot run in evaluation mode", "DATA_MODE_INVALID")
        history = read_history(request)
        rated = {feedback.movie_id for feedback in history.ratings}
        candidates: list[tuple[float, str]] = []
        for movie_id in self._top50:
            if movie_id in rated:
                continue
            candidates.append((self._scores[movie_id], movie_id))
            if len(candidates) >= request.limit:
                break
        items = [
            RecommendationItem(
                movie_id=movie_id,
                rank=index,
                algorithm=Algorithm.popular,
                model_version=MODEL_VERSION,
                score=score,
                recall_sources=["popular_bayesian"],
            )
            for index, (score, movie_id) in enumerate(candidates, 1)
        ]
        return RecommendationResult(
            algorithm=Algorithm.popular,
            model_version=MODEL_VERSION,
            dataset_version=DATASET,
            split_version=SPLIT,
            runtime_mode="business",
            generated_at=datetime.now(timezone.utc),
            items=items,
        )
