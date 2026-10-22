from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sys
from math import isfinite
from pathlib import Path

from recommender.business import read_history
from recommender.contracts import Algorithm, RecommendationItem, RecommendationRequest, RecommendationResult
from recommender.data import DATASET, SPLIT, require


MODEL_VERSION = "als-v1"
RECALL_SOURCE = "als:matrix_factorization"


def _solve_regularized_least_squares(Q, r, reg_param):
    n = len(Q)
    rank = len(Q[0])
    A = [[0.0] * rank for _ in range(rank)]
    b = [0.0] * rank
    for i in range(n):
        qi = Q[i]
        ri = r[i]
        for a in range(rank):
            qa = qi[a]
            b[a] += qa * ri
            for c in range(rank):
                A[a][c] += qa * qi[c]
    for a in range(rank):
        A[a][a] += reg_param

    aug = [row[:] + [b[a]] for a, row in enumerate(A)]
    for col in range(rank):
        pivot_row = col
        max_val = abs(aug[col][col])
        for row in range(col + 1, rank):
            if abs(aug[row][col]) > max_val:
                max_val = abs(aug[row][col])
                pivot_row = row
        aug[col], aug[pivot_row] = aug[pivot_row], aug[col]

        pivot = aug[col][col]
        if abs(pivot) < 1e-12:
            return [0.0] * rank

        for j in range(col, rank + 1):
            aug[col][j] /= pivot

        for row in range(rank):
            if row != col:
                factor = aug[row][col]
                if factor != 0.0:
                    for j in range(col, rank + 1):
                        aug[row][j] -= factor * aug[col][j]

    return [aug[i][rank] for i in range(rank)]


def _dot(u, v):
    return sum(a * b for a, b in zip(u, v))


@dataclass
class ALSProvider:
    model_manifest_path: Path

    def __post_init__(self):
        artifact_path = self.model_manifest_path.parent / "als_model.json"
        try:
            raw = json.loads(artifact_path.read_text(encoding="utf-8"))
            parameters = raw["parameters"]
            self._rank = int(parameters["rank"])
            self._reg_param = float(parameters["regParam"])
            self._max_iter = int(parameters["maxIter"])

            item_factors = {}
            for mid, features in raw["item_factors"].items():
                require(mid.isdigit(), "ALS item_id非法", "MODEL_BINDING_INVALID")
                require(len(features) == self._rank, "ALS特征维度不符", "MODEL_BINDING_INVALID")
                item_factors[mid] = tuple(float(v) for v in features)
            self._item_factors = item_factors

            user_factors = {}
            for uid, features in raw.get("user_factors", {}).items():
                require(uid.isdigit(), "ALS user_id非法", "MODEL_BINDING_INVALID")
                require(len(features) == self._rank, "ALS特征维度不符", "MODEL_BINDING_INVALID")
                user_factors[uid] = tuple(float(v) for v in features)
            self._user_factors = user_factors

            require(self._rank > 0 and self._reg_param >= 0.0 and self._max_iter > 0,
                    "ALS模型参数非法", "MODEL_BINDING_INVALID")
            require(len(item_factors) > 0, "ALS item_factors为空", "MODEL_BINDING_INVALID")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("ALS模型工件无法读取") from exc
        require(raw.get("model_version") == MODEL_VERSION and
                raw.get("algorithm") == Algorithm.als.value,
                "ALS模型版本或算法标识非法", "MODEL_BINDING_INVALID")

    def _compute_user_vector(self, ratings_dict):
        uid_key = str(ratings_dict.get("__uid", ""))
        if uid_key and uid_key in self._user_factors:
            return list(self._user_factors[uid_key])

        Q = []
        r = []
        for mid_str, rating in ratings_dict.items():
            if mid_str.startswith("__"):
                continue
            mid_str = str(mid_str)
            if mid_str in self._item_factors and isfinite(float(rating)):
                Q.append(list(self._item_factors[mid_str]))
                r.append(float(rating))

        if not Q:
            return [0.0] * self._rank

        return _solve_regularized_least_squares(Q, r, self._reg_param)

    def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        require(request.runtime_mode == "business", "ALS业务模型不能用于评价模式", "DATA_MODE_INVALID")
        history = read_history(request)

        ratings_dict = {}
        rated_set = set()
        if hasattr(history, "ratings") and history.ratings:
            for fb in history.ratings:
                mid = fb.movie_id
                ratings_dict[str(mid)] = float(fb.rating)
                rated_set.add(str(mid))

        user_vec = self._compute_user_vector(ratings_dict)

        raw_scores = []
        for mid, item_vec in self._item_factors.items():
            if mid in rated_set:
                continue
            score = _dot(user_vec, item_vec)
            raw_scores.append((score, int(mid), mid))

        raw_scores.sort(key=lambda t: (-t[0], t[1]))

        items = [
            RecommendationItem(
                movie_id=mid,
                rank=index,
                algorithm=Algorithm.als,
                model_version=MODEL_VERSION,
                score=round(max(0.0, min(1.0, score / 10.0)), 6),
                recall_sources=[RECALL_SOURCE],
            )
            for index, (score, _, mid) in enumerate(raw_scores[:request.limit], 1)
        ]
        return RecommendationResult(
            algorithm=Algorithm.als,
            model_version=MODEL_VERSION,
            dataset_version=DATASET,
            split_version=SPLIT,
            runtime_mode="business",
            generated_at=datetime.now(timezone.utc),
            items=items,
        )
