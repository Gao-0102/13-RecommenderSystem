import json
import os
from pathlib import Path
from typing import Any

import httpx

from recommender.business import read_history
from recommender.contracts import Algorithm, RecommendationRequest, PROVIDERS


def _top_n(items, key_fn, n, reverse=True):
    ranked = sorted(items, key=key_fn, reverse=reverse)
    return ranked[:n]


def collect_evidence(request: RecommendationRequest, algorithm: Algorithm, recommendations) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "subject": f"{request.subject_kind}:{request.subject_id}",
        "algorithm": algorithm.value,
        "user_ratings": [],
        "genre_profile": {},
        "seed_movies": [],
        "movie_evidence": [],
    }

    history = read_history(request)
    rated_list = [(fb.movie_id, float(fb.rating)) for fb in history.ratings]
    rated_list.sort(key=lambda x: -x[1])
    evidence["user_ratings"] = [
        {"movie_id": mid, "rating": rating} for mid, rating in rated_list[:20]
    ]

    rated_ids = {mid for mid, _ in rated_list}
    positive_seeds = [(mid, rating) for mid, rating in rated_list if rating >= 4.0]

    if algorithm in (Algorithm.content, Algorithm.rrf):
        content_provider = PROVIDERS.get(Algorithm.content)
        if content_provider is not None:
            profile = [0.0] * len(content_provider._genres)
            total_w = 0.0
            for mid, rating in positive_seeds:
                if mid not in content_provider._vectors:
                    continue
                w = rating - 3.0
                for i, v in enumerate(content_provider._vectors[mid]):
                    profile[i] += w * v
                total_w += w
            profile_norm = sum(v * v for v in profile) ** 0.5
            if profile_norm:
                normalized = [(content_provider._genres[i], round(profile[i] / profile_norm, 4))
                              for i in range(len(profile))]
                normalized.sort(key=lambda x: -x[1])
                evidence["genre_profile"] = dict(normalized[:10])

    if algorithm in (Algorithm.itemcf, Algorithm.rrf):
        itemcf_provider = PROVIDERS.get(Algorithm.itemcf)
        if itemcf_provider is not None:
            seed_list = []
            for mid, rating in positive_seeds:
                if mid in itemcf_provider._neighbors:
                    seed_list.append({"movie_id": mid, "rating": rating})
            evidence["seed_movies"] = seed_list[:15]

    if algorithm in (Algorithm.als, Algorithm.rrf):
        pass

    itemcf_provider = PROVIDERS.get(Algorithm.itemcf)
    for rec in recommendations:
        mid = rec.movie_id
        rec_info: dict[str, Any] = {"movie_id": mid, "rank": rec.rank, "score": rec.score}

        if algorithm in (Algorithm.content, Algorithm.rrf):
            content_provider = PROVIDERS.get(Algorithm.content)
            if content_provider is not None and mid in content_provider._vectors:
                vec = content_provider._vectors[mid]
                sim_items = []
                for hmid, hrating in positive_seeds:
                    if hmid not in content_provider._vectors:
                        continue
                    hv = content_provider._vectors[hmid]
                    dot = sum(a * b for a, b in zip(vec, hv))
                    nv = sum(a * a for a in vec) ** 0.5 or 1
                    nh = sum(a * a for a in hv) ** 0.5 or 1
                    cos = round(dot / (nv * nh), 4)
                    if cos > 0:
                        sim_items.append({"movie_id": hmid, "rating": hrating, "cosine_sim": cos})
                sim_items.sort(key=lambda x: -x["cosine_sim"])
                rec_info["content_evidence"] = sim_items[:3]

        if algorithm in (Algorithm.itemcf, Algorithm.rrf):
            if itemcf_provider is not None:
                icf_sources = []
                for hmid, hrating in positive_seeds:
                    if hmid in itemcf_provider._neighbors:
                        for target, sim, support in itemcf_provider._neighbors[hmid]:
                            if target == mid:
                                icf_sources.append({
                                    "from_movie": hmid,
                                    "user_rating": hrating,
                                    "similarity": round(sim, 4),
                                    "cooccurrence": support,
                                })
                icf_sources.sort(key=lambda x: -x["similarity"])
                rec_info["itemcf_evidence"] = icf_sources[:3]

        if algorithm == Algorithm.rrf and rec.recall_ranks:
            rec_info["rrf_sources"] = rec.recall_ranks

        evidence["movie_evidence"].append(rec_info)

    return evidence


SYSTEM_PROMPT = """你是一个推荐系统解释助手。你的任务是基于真实数据生成可核验的个性化推荐解释。

规则：
1. 所有分析必须基于证据提供的真实数据，严禁编造。
2. 解释要简洁、口语化，每部电影 1-2 句话。
3. 明确引用具体数字和电影 ID，方便核验。
4. 如果证据中缺少某类数据，明确说明"从 XX 角度看这部电影的证据不足"。
5. 按推荐排名从高到低依次解释 Top 5 电影。"""

ALGORITHM_GUIDE = {
    Algorithm.content.value: "基于内容相似：分析你历史高评分电影的类型构成，推荐与你兴趣画像类型匹配的电影。",
    Algorithm.itemcf.value: "基于物品协同过滤：喜欢了同一部电影的观众往往还喜欢其他电影，根据你的高分电影找邻居。",
    Algorithm.als.value: "基于矩阵分解：将你和电影映射到同一隐向量空间，内积分数越高越可能是你喜欢的。",
    Algorithm.rrf.value: "RRF 融合：综合 Content、ItemCF、ALS 三路候选，用排名倒数之和融合，综合多个视角的判断。",
    Algorithm.popular.value: "热门榜单：不个性化，基于评分数量和分布加权后排序。",
    Algorithm.cold_start.value: "冷启动：新用户无足够历史时的推荐策略。",
}


def build_prompt(evidence: dict, algorithm: Algorithm) -> tuple[str, str]:
    user_ratings = evidence["user_ratings"]
    genre_profile = evidence.get("genre_profile", {})
    seed_movies = evidence.get("seed_movies", [])
    movie_evidence = evidence["movie_evidence"]

    lines = []
    lines.append(f"## 用户画像")
    lines.append(f"用户：{evidence['subject']}")
    lines.append(f"历史评分（前20部，只展示有评分的）：")
    for item in user_ratings[:10]:
        lines.append(f"  电影 {item['movie_id']}: 评分 {item['rating']}")
    lines.append("")

    if genre_profile:
        lines.append(f"Content 类型画像 Top 10（权重已归一化）：")
        for g, w in genre_profile.items():
            lines.append(f"  {g}: {w}")
        lines.append("")

    if seed_movies:
        lines.append(f"ItemCF 种子（评分 ≥ 4.0 的正反馈）：")
        for s in seed_movies[:5]:
            lines.append(f"  电影 {s['movie_id']}: 评分 {s['rating']}")
        lines.append("")

    lines.append(f"## 推荐算法说明")
    lines.append(ALGORITHM_GUIDE.get(algorithm.value, ""))
    lines.append("")

    lines.append(f"## 推荐结果及证据")
    for me in movie_evidence[:5]:
        lines.append(f"### 排名 #{me['rank']} · 电影 {me['movie_id']} (融合分 {me['score']})")
        if "content_evidence" in me:
            lines.append("Content 角度——与你的高分电影最相似的类型邻居：")
            for ce in me["content_evidence"]:
                lines.append(f"  和你评 {ce['rating']} 的电影 {ce['movie_id']} 类型余弦相似度 {ce['cosine_sim']}")
        if "itemcf_evidence" in me:
            lines.append("ItemCF 角度——来自你的高分电影邻居：")
            for ie in me["itemcf_evidence"]:
                lines.append(f"  因你喜欢电影 {ie['from_movie']}(评分{ie['user_rating']})，相似度 {ie['similarity']}，共现 {ie['cooccurrence']} 次")
        if "rrf_sources" in me:
            lines.append(f"RRF 来源排名：{json.dumps(me['rrf_sources'], ensure_ascii=False)}")
        lines.append("")

    prompt_text = "\n".join(lines)
    return SYSTEM_PROMPT, prompt_text


def call_llm(system_prompt: str, user_prompt: str, timeout: float = 30.0) -> str:
    endpoint = os.getenv("APP_LLM_ENDPOINT", "")
    api_key = os.getenv("APP_LLM_API_KEY", "")
    model = os.getenv("APP_LLM_MODEL", "deepseek-chat")

    if not endpoint or not api_key:
        return (
            "LLM API 未配置。请在后端环境变量中设置：\n"
            "  APP_LLM_ENDPOINT=https://api.deepseek.com/v1/chat/completions\n"
            "  APP_LLM_API_KEY=sk-xxx\n"
            "  APP_LLM_MODEL=deepseek-chat\n\n"
            f"以下是可核验的原始证据数据（替代自然语言解释）：\n\n{user_prompt}"
        )

    url = endpoint
    if not url.endswith("/chat/completions"):
        if not url.endswith("/"):
            url += "/"
        url += "chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 1200,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        return f"LLM 调用失败 ({type(exc).__name__}): {exc}\n\n--- 原始证据数据 ---\n\n{user_prompt}"
