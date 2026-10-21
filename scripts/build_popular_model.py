import csv
import json
from collections import defaultdict
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
train_path = PACKAGE / "data/packages/rec-course-v3-train5-1.0.0/evaluation/train.csv"

movie_ratings = defaultdict(list)
with train_path.open(encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        movie_ratings[row["movieId"]].append(float(row["rating"]))

stats = {}
for mid, ratings in movie_ratings.items():
    v = len(ratings)
    R = sum(ratings) / v
    stats[mid] = (R, v)

global_mean_rating = sum(R for R, v in stats.values()) / len(stats)

sorted_counts = sorted(v for _, v in stats.values())
C = sorted_counts[int(len(sorted_counts) * 0.9)]

print(f"电影总数: {len(stats)}")
print(f"全局平均分: {global_mean_rating:.4f}")
print(f"先验人数 C (90%分位): {C}")
print(f"总评分数: {sum(v for _, v in stats.values())}")

scored = []
for mid, (R, v) in stats.items():
    bayesian = (C * global_mean_rating + R * v) / (C + v)
    scored.append((bayesian, R, v, mid))

scored.sort(key=lambda x: (-x[0], int(x[3])))

print("\n=== Top 20 热门电影 (贝叶斯平均) ===")
for i, (score, R, v, mid) in enumerate(scored[:20], 1):
    print(f"{i:2d}. movie_id={mid:>5s}  bayesian={score:.4f}  mean={R:.3f}  count={v}")

MIN_RATING = 1.0
MAX_RATING = 5.0

top50 = [
    {
        "movie_id": mid,
        "bayesian_score": round(score, 6),
        "normalized_score": round((score - MIN_RATING) / (MAX_RATING - MIN_RATING), 6),
        "avg_rating": round(R, 4),
        "rating_count": v,
    }
    for score, R, v, mid in scored[:50]
]

out = {
    "model_version": "popular-v1",
    "algorithm": "popular",
    "global_mean_rating": round(global_mean_rating, 6),
    "prior_count_C": C,
    "rating_range": {"min": MIN_RATING, "max": MAX_RATING},
    "bayesian_top50": top50,
}

out_dir = PACKAGE / "models/business/popular-v1"
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / "popular_model.json").write_text(
    json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
)

print(f"\n已写入 {out_dir / 'popular_model.json'}")
