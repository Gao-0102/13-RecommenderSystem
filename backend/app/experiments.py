from typing import Annotated
import json
from pathlib import Path

from fastapi import APIRouter, Query, Request
from pydantic import Field
from sqlalchemy import text

from recommender.contracts import Algorithm, AlgorithmNotImplemented, RecommendationRequest, RecommendationResult, PROVIDERS, recommend
from recommender.data import ContractError
from .config import DATASET, SPLIT
from .errors import APIError
from .schemas import IdPath, Input, identifier
from .security import ActorDependency

router = APIRouter(tags=["学生算法预留边界"])


class RecommendationQuery(Input):
    limit: int = Field(default=10, ge=1, le=50)


_RRF_REGISTERED = {Algorithm.rrf.value}


def invoke(algorithm: Algorithm, kind: str, uid: int, limit: int):
    request = RecommendationRequest(kind, uid, limit, "business", DATASET, SPLIT)
    if algorithm == Algorithm.rrf:
        from recommender.student.rrf import rrf_fuse
        try:
            return rrf_fuse(request)
        except ContractError as exc:
            raise APIError(503 if exc.code in {"MODEL_BINDING_INVALID", "DATA_IDENTITY_INVALID", "DATA_MODE_INVALID"} else 500,
                exc.code, str(exc)) from None
    try:
        return recommend(algorithm, request)
    except AlgorithmNotImplemented:
        raise APIError(501, "ALGORITHM_NOT_IMPLEMENTED", "此推荐算法留给学生实现", {
            "status": "not_implemented", "algorithm": algorithm.value, "subject_key": kind + ":" + str(uid),
            "dataset_version": DATASET, "split_version": SPLIT, "runtime_mode": "business",
            "model_version": None, "batch_id": None, "items": []}) from None
    except ContractError as exc:
        raise APIError(503 if exc.code in {"MODEL_BINDING_INVALID", "DATA_IDENTITY_INVALID", "DATA_MODE_INVALID"} else 500,
            exc.code, str(exc)) from None


@router.get("/experiments/algorithms")
def algorithms():
    items = []
    for algorithm in Algorithm:
        if algorithm in PROVIDERS or algorithm.value in _RRF_REGISTERED:
            status = "registered"
        else:
            status = "not_implemented"
        items.append({"algorithm": algorithm.value, "status": status})
    return {"items": items}


@router.get("/experiments/evaluations")
def evaluations():
    metrics_path = Path("/app/models/business/eval_metrics.json")
    if metrics_path.exists():
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
        return data
    raise APIError(501, "EVALUATION_NOT_IMPLEMENTED", "评价模型文件不存在，请先运行 scripts/build_eval_metrics.py", {
        "status": "not_implemented", "metrics": None, "dataset_version": DATASET, "split_version": SPLIT})


@router.get("/me/recommendations/{algorithm}", response_model=RecommendationResult)
def my_recommendations(algorithm: Algorithm, actor: ActorDependency, query: Annotated[RecommendationQuery, Query()]):
    return invoke(algorithm, "app", actor.account_id, query.limit)


@router.get("/demo/history-users/{ml_user_id}/recommendations/{algorithm}", response_model=RecommendationResult)
def history_recommendations(ml_user_id: IdPath, algorithm: Algorithm, request: Request,
                            query: Annotated[RecommendationQuery, Query()]):
    uid = identifier(ml_user_id)
    with request.app.state.db.connection() as conn:
        if conn.execute(text("SELECT ml_user_id FROM history_users WHERE ml_user_id=:id"), {"id": uid}).first() is None:
            raise APIError(404, "HISTORY_USER_NOT_FOUND", "历史匿名用户不存在")
    return invoke(algorithm, "ml", uid, query.limit)


@router.get("/me/recommendations/{algorithm}/explain")
def my_explain(algorithm: Algorithm, actor: ActorDependency, query: Annotated[RecommendationQuery, Query()]):
    return _explain_for(algorithm, "app", actor.account_id, query.limit)


@router.get("/demo/history-users/{ml_user_id}/recommendations/{algorithm}/explain")
def history_explain(ml_user_id: IdPath, algorithm: Algorithm, request: Request,
                    query: Annotated[RecommendationQuery, Query()]):
    uid = identifier(ml_user_id)
    with request.app.state.db.connection() as conn:
        if conn.execute(text("SELECT ml_user_id FROM history_users WHERE ml_user_id=:id"), {"id": uid}).first() is None:
            raise APIError(404, "HISTORY_USER_NOT_FOUND", "历史匿名用户不存在")
    return _explain_for(algorithm, "ml", uid, query.limit)


def _explain_for(algorithm: Algorithm, kind: str, uid: int, limit: int):
    result = invoke(algorithm, kind, uid, limit)
    from recommender.contracts import RecommendationRequest
    request = RecommendationRequest(kind, uid, limit, "business", DATASET, SPLIT)
    from .explain import collect_evidence, build_prompt, call_llm
    evidence = collect_evidence(request, algorithm, result.items)
    system_prompt, user_prompt = build_prompt(evidence, algorithm)
    explanation = call_llm(system_prompt, user_prompt)
    return {
        "algorithm": algorithm.value,
        "explanation": explanation,
        "evidence": evidence,
        "prompt_preview": user_prompt[:800],
    }
