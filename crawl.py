"""매물 크롤러: 조건(시세 대비 싼 매물)에 맞는 것만 items.json 으로 저장.
GitHub Actions에서 주기적으로 실행됨. 사이트 구조가 바뀌면 각 함수만 고치면 됨.
"""
import json, re, time, requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari"}

# 조건은 코드가 아니라 config.json 에서 수정 (GitHub 웹에서 연필 아이콘으로 편집)
CFG = json.load(open("config.json", encoding="utf-8"))
MARKET = CFG["market"]
MIN_PROFIT = CFG["min_profit"]
BAD_WORDS = CFG["bad_words"]
MIN_PRICE = CFG.get("min_price", 30000)


def bunjang(q):
    r = requests.get("https://api.bunjang.co.kr/api/1/find_v2.json",
                     params={"q": q, "order": "date", "page": 0, "n": 60, "req_ref": "search"},
                     headers=UA, timeout=15)
    out = []
    for p in r.json().get("list", []):
        pid = p["pid"]
        img = (p.get("product_image") or "").replace("{cnt}", "1").replace("{res}", "400")
        out.append(dict(id=f"bj{pid}", source="번개장터", title=p["name"], price=int(p["price"] or 0),
                        images=[img] if img else [], url=f"https://m.bunjang.co.kr/products/{pid}",
                        location=p.get("location", ""), seller="번개장터 판매자", description=""))
    return out


def daangn(q):
    # 당근은 공식 API가 없어 검색 페이지의 __NEXT_DATA__ JSON을 파싱 (구조 바뀌면 수정 필요)
    r = requests.get("https://www.daangn.com/kr/buy-sell/", params={"search": q}, headers=UA, timeout=15)
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    out = []
    if not m:
        return out
    data = json.loads(m.group(1))
    arts = data.get("props", {}).get("pageProps", {}).get("dehydratedState", {})
    # 실제 경로는 페이지마다 달라서 'price' 와 'title' 이 있는 dict를 재귀로 탐색
    def walk(o):
        if isinstance(o, dict):
            if "title" in o and "price" in o and "href" in o:
                yield o
            for v in o.values():
                yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v)
    for a in walk(arts):
        try:
            out.append(dict(id="dg" + re.sub(r"\W", "", a["href"])[-12:], source="당근마켓", title=a["title"],
                            price=int(float(a["price"])), images=[a["thumbnail"]] if a.get("thumbnail") else [],
                            url=a["href"] if a["href"].startswith("http") else "https://www.daangn.com" + a["href"],
                            location=(a.get("region") or {}).get("name", "") if isinstance(a.get("region"), dict) else "",
                            seller="당근 이웃", description=a.get("content", "")))
        except Exception:
            continue
    return out


def joongna(q):
    # 중고나라 웹 검색 내부 API (변경될 수 있음)
    r = requests.post("https://search-api.joongna.com/v25/search/product",
                      json={"searchWord": q, "page": 0, "quantity": 40, "sort": "RECENT_SORT"},
                      headers={**UA, "Content-Type": "application/json"}, timeout=15)
    out = []
    for p in r.json().get("data", {}).get("items", []):
        seq = p["seq"]
        out.append(dict(id=f"jn{seq}", source="중고나라", title=p["title"], price=int(p["price"] or 0),
                        images=[p["url"]] if p.get("url") else [],
                        url=f"https://web.joongna.com/product/{seq}",
                        location=p.get("locationNames", [""])[0] if p.get("locationNames") else "",
                        seller=p.get("storeName", "중고나라 판매자"), description=""))
    return out


def market_price(title):
    t = title.lower()
    for k, v in MARKET.items():      # 위에서부터 구체적인 키워드 먼저 매칭
        if all(w in t for w in k.replace("닌텐도 ", "").split()):
            return v
    return 0


def main():
    found = {}
    for q in MARKET:
        for fn in (bunjang, daangn, joongna):
            try:
                for it in fn(q):
                    found[it["id"]] = it
            except Exception as e:
                print(f"[skip] {fn.__name__} '{q}': {e}")
            time.sleep(1.5)  # 서버에 부담 안 주기

    good = []
    for it in found.values():
        if any(w in it["title"] for w in BAD_WORDS) or it["price"] < MIN_PRICE:
            continue
        mp = market_price(it["title"])
        if mp and mp - it["price"] >= MIN_PROFIT:
            it.update(market_price=mp, deal_count=0, manner=0)
            good.append(it)
    good.sort(key=lambda x: x["market_price"] - x["price"], reverse=True)
    json.dump(good, open("items.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(good)}개 저장")


if __name__ == "__main__":
    main()
