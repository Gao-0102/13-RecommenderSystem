"""Generate pre-computed evaluation metrics JSON for backend."""
import csv, json, numpy as np, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "data/packages/rec-course-v3-train5-1.0.0"
ALS_MODEL = ROOT / "models/evaluation/als-train5-v1/als_model.json"
CONTENT_MODEL = ROOT / "models/business/content-genre-v1/content_model.json"
ITEMCF_MODEL = ROOT / "models/business/itemcf-v1/itemcf_model.json"
POPULAR_MODEL = ROOT / "models/business/popular-v1/popular_model.json"
OUT = ROOT / "models/business/eval_metrics.json"

print("Loading data...")
als_raw = json.loads(ALS_MODEL.read_text())
content_raw = json.loads(CONTENT_MODEL.read_text())
itemcf_raw = json.loads(ITEMCF_MODEL.read_text())
popular_raw = json.loads(POPULAR_MODEL.read_text())
neighbors_map = itemcf_raw["item_neighbors"]

als_reg = als_raw["parameters"]["regParam"]
als_mids_sorted = sorted(als_raw["item_factors"].keys())
als_idx = {m: i for i, m in enumerate(als_mids_sorted)}
als_item_mat = np.stack([np.array(als_raw["item_factors"][m], dtype=np.float64) for m in als_mids_sorted])

train = {}
with open(PKG/"evaluation/train.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        uid=int(r["userId"]); mid=r["movieId"]; rt=float(r["rating"])
        train.setdefault(uid, {})[mid]=rt
val = {}
with open(PKG/"evaluation/validation.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        uid=int(r["userId"]); mid=r["movieId"]
        val.setdefault(uid, set()).add(mid)

eval_users = [uid for uid in val if uid in train]
print(f"  eval users: {len(eval_users)}")

# Content preprocess
c_mids = sorted(content_raw["movie_vectors"].keys(), key=lambda x: int(x))
c_vectors = np.stack([np.array(content_raw["movie_vectors"][m], dtype=np.float64) for m in c_mids])
c_mids_arr = np.array([int(m) for m in c_mids])
c_genres = content_raw["genres"]

def find_content_pos(mid_str):
    im = int(mid_str)
    pos = np.searchsorted(c_mids_arr, im)
    if pos < len(c_mids_arr) and c_mids_arr[pos] == im: return pos
    return -1

# ALS fold-in
print("ALS fold-in...")
als_valid_users = 0
als_hits = []
for uid in eval_users:
    hist = train[uid]
    indices = [als_idx[str(m)] for m in hist if str(m) in als_idx]
    sub_r = np.array([hist[m] for m in hist if str(m) in als_idx])
    if len(indices) < 3: continue
    sub_Q = als_item_mat[indices]
    uv = np.linalg.solve(sub_Q.T @ sub_Q + als_reg * np.eye(sub_Q.shape[1]), sub_Q.T @ sub_r)
    scores = als_item_mat @ uv
    seen = set(str(m) for m in hist)
    for i, m in enumerate(als_mids_sorted):
        if m in seen: scores[i] = -1e18
    top10 = [als_mids_sorted[i] for i in np.argsort(-scores)[:10]]
    gt = val[uid]
    als_hits.append(sum(1 for m in top10 if m in gt))
    als_valid_users += 1
als_p = np.mean(als_hits) / 10.0
als_r = np.mean(als_hits) / np.mean([len(val[u]) for u in eval_users[:len(als_hits)]])
print(f"  ALS: P@10={als_p:.4f}  R@10={als_r:.4f}")

# Content rating-weighted profile
print("Content rating-weighted...")
c_hits = []
for uid in eval_users:
    hist = train[uid]
    vecs_h, rates_h, mid_h = [], [], []
    for mid, rt in hist.items():
        pos = find_content_pos(mid)
        if pos >= 0:
            vecs_h.append(c_vectors[pos]); rates_h.append(rt); mid_h.append(mid)
    if len(vecs_h) < 2: continue
    Q = np.array(vecs_h); r = np.array(rates_h)
    rs = r.sum()
    if rs <= 0: continue
    profile = (Q.T @ r) / rs
    pn = np.linalg.norm(profile)
    if pn < 1e-12: continue
    profile_n = profile / pn
    cnorms = np.linalg.norm(c_vectors, axis=1)
    cnorms_safe = np.where(cnorms > 1e-12, cnorms, 1.0)
    cos = (c_vectors @ profile_n) / cnorms_safe
    seen = set(str(m) for m in hist)
    mask = np.array([str(int(c_mids_arr[i])) in seen or cnorms[i] < 1e-12 for i in range(len(c_mids_arr))])
    cos = np.where(mask, -1e18, cos)
    top10 = [int(c_mids_arr[i]) for i in np.argsort(-cos)[:10]]
    gt = val[uid]
    c_hits.append(sum(1 for m in top10 if str(m) in gt))
c_p = np.mean(c_hits) / 10.0
c_r = np.mean(c_hits) / np.mean([len(val[u]) for u in eval_users[:len(c_hits)]])
print(f"  Content: P@10={c_p:.4f}  R@10={c_r:.4f}")

# ItemCF
print("ItemCF...")
itemcf_valid_users = 0
itemcf_hits = []

for i, uid in enumerate(eval_users):
    if i % 500 == 0: print(f"    {i}/{len(eval_users)}...")
    hist = train[uid]
    scores = {}
    for mid, rt in hist.items():
        if mid in neighbors_map:
            for nb in neighbors_map[mid]:
                target = nb["movie_id"]
                if target in hist: continue
                sim = nb["similarity"]
                if sim > 0:
                    scores[target] = scores.get(target, 0.0) + sim * (rt - 3.0)
    seen = set(str(m) for m in hist.keys())
    cands = [(s, m) for m, s in scores.items() if str(m) not in seen and s > 0]
    cands.sort(key=lambda x: -x[0])
    top10 = [str(c[1]) for c in cands[:10]]
    if not top10: continue
    gt = val[uid]
    itemcf_hits.append(sum(1 for m in top10 if m in gt))
    itemcf_valid_users += 1
ic_p = np.mean(itemcf_hits) / 10.0 if itemcf_hits else 0.0
ic_r = np.mean(itemcf_hits) / np.mean([len(val[u]) for u in eval_users[:len(itemcf_hits)]]) if itemcf_hits else 0.0
print(f"  ItemCF: P@10={ic_p:.4f}  R@10={ic_r:.4f}")

# Popular (Bayesian top-50)
print("Popular (Bayesian)...")
popular_top50 = [str(item["movie_id"]) for item in popular_raw["bayesian_top50"]]
popular_hits = []
for uid in eval_users:
    seen = set(str(m) for m in train[uid].keys())
    top10 = [m for m in popular_top50 if m not in seen][:10]
    if len(top10) < 10: continue
    gt = val[uid]
    popular_hits.append(sum(1 for m in top10 if m in gt))
p_p = np.mean(popular_hits) / 10.0
p_r = np.mean(popular_hits) / np.mean([len(val[u]) for u in eval_users[:len(popular_hits)]])
print(f"  Popular: P@10={p_p:.4f}  R@10={p_r:.4f}")

# Build output
result = {
    "status": "evaluated",
    "metrics": {
        "dataset_version": "rec-course-v3-train5-1.0.0",
        "split_version": "temporal-v1-cold500-train5-v3",
        "evaluation_file": "evaluation/validation.csv",
        "train_file": "evaluation/train.csv",
        "user_count": len(eval_users),
        "top_k": 10,
        "algorithms": [
            {
                "algorithm": "content",
                "name": "内容推荐 (Content-Based)",
                "precision_at_10": round(c_p, 6),
                "recall_at_10": round(c_r, 6),
                "valid_users": len(c_hits),
                "description": "基于电影 genre 向量的余弦相似度推荐，使用用户历史评分加权生成偏好画像"
            },
            {
                "algorithm": "itemcf",
                "name": "Item 协同过滤 (ItemCF)",
                "precision_at_10": round(ic_p, 6),
                "recall_at_10": round(ic_r, 6),
                "valid_users": itemcf_valid_users,
                "description": "基于物品相似度的加权评分预测，使用物品间共现相似度为用户历史物品打分"
            },
            {
                "algorithm": "als",
                "name": "ALS 矩阵分解",
                "precision_at_10": round(als_p, 6),
                "recall_at_10": round(als_r, 6),
                "valid_users": als_valid_users,
                "description": "使用交替最小二乘法 (ALS) 学习用户/物品隐向量，通过 dot product 评分排序"
            },
            {
                "algorithm": "popular",
                "name": "热门推荐 (Bayesian Popularity)",
                "precision_at_10": round(p_p, 6),
                "recall_at_10": round(p_r, 6),
                "valid_users": len(popular_hits),
                "description": "基于贝叶斯平均评分的全局 Top-50 热门榜，对所有用户相同（去除已评电影）"
            }
        ]
    }
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nSaved to {OUT}")
print(json.dumps(result, indent=2, ensure_ascii=False))
