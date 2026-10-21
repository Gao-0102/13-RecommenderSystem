from dataclasses import dataclass
from datetime import datetime, timezone
import json
from math import isfinite
from pathlib import Path

from recommender.business import read_history
from recommender.contracts import Algorithm, RecommendationItem, RecommendationRequest, RecommendationResult
from recommender.data import DATASET, SPLIT, require


MODEL_VERSION = "itemcf-v1"
RECALL_SOURCE = "itemcf:positive_rating_cooccurrence"


@dataclass
class ItemCFProvider:
    model_manifest_path: Path

    def __post_init__(self):
        artifact_path = self.model_manifest_path.parent / "itemcf_model.json"
        try:
            raw = json.loads(artifact_path.read_text(encoding="utf-8"))
            parameters = raw["parameters"]
            self._positive_threshold = float(parameters["positive_rating_threshold"])
            self._min_cooccurrence = int(parameters["min_cooccurrence"])
            self._neighbor_size = int(parameters["neighbor_size"])
            neighbors = {}
            for source_id, entries in raw["item_neighbors"].items():
                require(source_id.isdigit(), "ItemCF源电影ID非法", "MODEL_BINDING_INVALID")
                parsed = []
                previous_key = None
                for entry in entries:
                    target_id = str(entry["movie_id"])
                    support = int(entry["cooccurrence"])
                    similarity = float(entry["similarity"])
                    require(target_id.isdigit() and target_id != source_id and
                            isfinite(similarity) and 0.0 < similarity <= 1.0 and
                            support >= self._min_cooccurrence,
                            "ItemCF邻居工件非法", "MODEL_BINDING_INVALID")
                    order_key = (-similarity, int(target_id))
                    require(previous_key is None or previous_key < order_key,
                            "ItemCF邻居顺序或唯一性非法", "MODEL_BINDING_INVALID")
                    previous_key = order_key
                    parsed.append((target_id, similarity, support))
                require(len(parsed) <= self._neighbor_size, "ItemCF邻居数量超过参数", "MODEL_BINDING_INVALID")
                neighbors[source_id] = tuple(parsed)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("ItemCF模型工件无法读取") from exc
        require(raw.get("model_version") == MODEL_VERSION and
                raw.get("algorithm") == Algorithm.itemcf.value and
                self._positive_threshold == 4.0 and
                self._min_cooccurrence >= 1 and self._neighbor_size >= 1 and neighbors,
                "ItemCF模型工件版本或参数非法", "MODEL_BINDING_INVALID")
        self._neighbors = neighbors

    def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        require(request.runtime_mode == "business", "ItemCF业务模型不能用于评价模式", "DATA_MODE_INVALID")
        history = read_history(request)
        rated = {}
        positive_seeds = []
        for feedback in history.ratings:
            movie_id = feedback.movie_id
            rating = float(feedback.rating)
            rated[movie_id] = rating
            if rating >= self._positive_threshold and movie_id in self._neighbors:
                positive_seeds.append((movie_id, rating))

        scores = {}
        total_seed_weight = sum(rating - 3.0 for _, rating in positive_seeds)
        for source_id, rating in positive_seeds:
            seed_weight = rating - 3.0
            for target_id, similarity, _ in self._neighbors[source_id]:
                if target_id in rated:
                    continue
                scores[target_id] = scores.get(target_id, 0.0) + similarity * seed_weight

        candidates = sorted(
            ((round(score / total_seed_weight, 9), int(movie_id), movie_id) for movie_id, score in scores.items()),
            key=lambda item: (-item[0], item[1]),
        )
        items = [
            RecommendationItem(
                movie_id=movie_id,
                rank=index,
                algorithm=Algorithm.itemcf,
                model_version=MODEL_VERSION,
                score=score,
                recall_sources=[RECALL_SOURCE],
            )
            for index, (score, _, movie_id) in enumerate(candidates[:request.limit], 1)
        ]
        return RecommendationResult(
            algorithm=Algorithm.itemcf,
            model_version=MODEL_VERSION,
            dataset_version=DATASET,
            split_version=SPLIT,
            runtime_mode="business",
            generated_at=datetime.now(timezone.utc),
            items=items,
        )
