from datetime import datetime, timezone

from recommender.contracts import Algorithm, RecommendationItem, RecommendationRequest, RecommendationResult, PROVIDERS


MODEL_VERSION = "rrf-v1"
RRF_K = 60
FUSION_SOURCES = [Algorithm.content, Algorithm.itemcf, Algorithm.als]


def rrf_fuse(request: RecommendationRequest) -> RecommendationResult:
    fused_limit = min(request.limit * 3, 50)
    merged: dict[str, dict] = {}

    for alg in FUSION_SOURCES:
        provider = PROVIDERS.get(alg)
        if provider is None:
            continue
        sub_request = RecommendationRequest(
            request.subject_kind, request.subject_id, fused_limit,
            request.runtime_mode, request.dataset_version, request.split_version,
        )
        try:
            result = provider.recommend(sub_request)
        except Exception:
            continue
        for item in result.items:
            movie_id = item.movie_id
            contribution = 1.0 / (RRF_K + item.rank)
            if movie_id not in merged:
                merged[movie_id] = {
                    "score": 0.0,
                    "sources": [],
                    "ranks": {},
                }
            merged[movie_id]["score"] += contribution
            merged[movie_id]["sources"].append(alg.value)
            merged[movie_id]["ranks"][alg.value] = item.rank

    ranked = sorted(merged.items(), key=lambda kv: (-kv[1]["score"], int(kv[0])))

    items = [
        RecommendationItem(
            movie_id=movie_id,
            rank=idx,
            algorithm=Algorithm.rrf,
            model_version=MODEL_VERSION,
            score=round(data["score"], 9),
            recall_sources=sorted(set(data["sources"])),
            recall_ranks=data["ranks"],
        )
        for idx, (movie_id, data) in enumerate(ranked[: request.limit], 1)
    ]

    from recommender.data import DATASET, SPLIT

    return RecommendationResult(
        algorithm=Algorithm.rrf,
        model_version=MODEL_VERSION,
        dataset_version=DATASET,
        split_version=SPLIT,
        runtime_mode="business",
        generated_at=datetime.now(timezone.utc),
        items=items,
    )
