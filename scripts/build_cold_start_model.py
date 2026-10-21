"""Build cold-start model artifact by embedding popular top50."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
popular_path = ROOT / "models" / "business" / "popular-v1" / "popular_model.json"
out_dir = ROOT / "models" / "business" / "cold-start-v1"
out_path = out_dir / "cold_start_model.json"

out_dir.mkdir(parents=True, exist_ok=True)

popular = json.loads(popular_path.read_text(encoding="utf-8"))

artifact = {
    "model_version": "cold-start-v1",
    "popular_top50": popular["bayesian_top50"],
    "popular_source_version": popular.get("model_version", "popular-v1"),
    "routes": {
        "cold": {
            "condition": "positive_ratings == 0",
            "strategy": "popular",
            "description": "新用户无历史正反馈，返回热门榜单",
        },
        "warm": {
            "condition": "positive_ratings >= 1",
            "strategy": "content",
            "description": "有少量正反馈，切到内容推荐",
        },
    },
    "parameters": {
        "positive_rating_threshold": 4.0,
        "top_n": 50,
    },
}

out_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"已写入 {out_path}")
print(f"内嵌热门电影数: {len(artifact['popular_top50'])}")
