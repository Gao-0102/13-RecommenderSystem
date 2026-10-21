import urllib.request, json
for uid in [14, 99999]:
    try:
        url = f"http://127.0.0.1:8000/api/v1/demo/history-users/{uid}/recommendations/cold_start?limit=5"
        r = urllib.request.urlopen(url, timeout=20)
        data = json.loads(r.read())
        items = data["items"]
        srcs = set()
        for i in items:
            for s in (i.get("recall_sources") or []):
                srcs.add(s)
        first = items[0]["movie_id"] if items else "none"
        print(f"user={uid}: {len(items)} items, sources={srcs}, first_movie={first}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        print(f"user={uid}: HTTP {e.code}: {body}")
