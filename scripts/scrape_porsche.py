"""포르쉐코리아 모델 페이지 → data/porsche/*.json

모델 개요 페이지의 트림(모델 버전) 링크를 모으고, 각 트림 페이지에 들어 있는 구조화 데이터(JSON-LD Car)에서
권장 가격·구동·가속·최고속도·크기를 읽는다. 포르쉐는 대부분의 장비가 개별 선택 옵션이라 트림별 기본 품목표는 없다.
"""
import json
import re

from common import DATA, curl_get, save

BASE = "https://www.porsche.com/korea/ko/models/"
# 모델 라인 → (모델 이름, 차급), 두 번째 경로 → 변형 이름
LINES = {
    "911": ("911", "쿠페"), "718": ("718", "로드스터"), "taycan": ("Taycan", "전기 4도어 쿠페"),
    "panamera": ("Panamera", "4도어 쿠페"), "macan": ("Macan Electric", "전기 SUV"),
    "cayenne": ("Cayenne", "SUV"), "cayenne-e": ("Cayenne Electric", "전기 SUV"),
}
BODY = {"carrera-models": "Carrera", "carrera-cabriolet-models": "Carrera 카브리올레", "targa-models": "Targa",
        "911-gt3-models": "GT3", "911-spirit-70": "Spirit 70", "911-turbo-models": "Turbo", "718-models": "718",
        "taycan-models": "세단", "taycan-black-edition": "Black Edition", "taycan-cross-turismo-models": "Cross Turismo",
        "panamera-models": "Panamera", "macan-electric-models": "Macan Electric", "cayenne-models": "SUV",
        "cayenne-coupe-models": "쿠페", "cayenne-black-edition": "Black Edition", "cayenne-electric-models": "SUV",
        "cayenne-coupe-electric-models": "쿠페"}
FUEL = {"FUEL": "가솔린", "ELECTRIC": "전기", "HYBRID": "플러그인 하이브리드", "PLUGIN_HYBRID": "플러그인 하이브리드"}


def car_ld(html):
    for s in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            d = json.loads(s)
        except Exception:
            continue
        for x in (d if isinstance(d, list) else d.get("@graph", [d])):
            if isinstance(x, dict) and x.get("offers") and "Car" in str(x.get("@type")):
                return x
    return None


def qv(x):
    return f"{x['value']:,}" if isinstance(x, dict) and isinstance(x.get("value"), (int, float)) and x["value"] >= 1000 \
        else (x.get("value") if isinstance(x, dict) else None)


def main():
    html = curl_get(BASE, cache=False)
    links = sorted(set(re.findall(r'/korea/ko/models/([a-z0-9-]+/[a-z0-9-]+/(?:[a-z0-9-]+/)?)', html)))
    links = [l for l in links if "configure" not in l and l.count("/") >= 2]
    models = {}
    for l in links:
        parts = l.strip("/").split("/")
        line, body = parts[0], parts[1]
        try:
            car = car_ld(curl_get(BASE + l))
        except Exception as e:
            print(l, "error", e)
            continue
        if not car:
            continue
        price = (car.get("offers") or [{}])[0].get("price")
        if not price:
            continue
        key = "cayenne-e" if line == "cayenne" and "electric" in body else line
        name, seg = LINES.get(key, (line.title(), "쿠페"))
        fuel = "플러그인 하이브리드" if "e-hybrid" in l else FUEL.get(car.get("fuelType"), car.get("fuelType") or "")
        items = [{"n": f"연료: {fuel}"}, {"n": f"구동: {car.get('driveWheelConfiguration')}"}] if car.get("driveWheelConfiguration") else [{"n": f"연료: {fuel}"}]
        perf = []
        if qv(car.get("accelerationTime")):
            perf.append({"n": f"0→100km/h {qv(car['accelerationTime'])}초"})
        if qv(car.get("speed")):
            perf.append({"n": f"최고속도 {qv(car['speed'])}km/h"})
        dims = [{"n": f"{lab} {qv(car[k])}mm"} for k, lab in (("length", "전장"), ("width", "전폭"), ("height", "전고"), ("wheelbase", "축거")) if qv(car.get(k))]
        trim = {"name": car.get("name") or parts[-1], "price": int(price),
                "cats": [c for c in ({"cat": "파워트레인", "items": items}, {"cat": "성능", "items": perf}, {"cat": "제원", "items": dims}) if c["items"]],
                "adds": [], "opts": []}
        m = models.setdefault(name, {"seg": seg, "variants": {}, "img": None, "src": []})
        m["variants"].setdefault(BODY.get(body, body), []).append(trim)
        m["src"].append(BASE + l)
        if not m["img"] and car.get("image"):
            m["img"] = car["image"]
    out = DATA / "porsche"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    for name, m in models.items():
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        variants = [{"name": vn, "code": slug, "trims": sorted(ts, key=lambda t: t["price"])} for vn, ts in m["variants"].items()]
        d = {"id": f"porsche-{slug}", "brand": "porsche", "name": name, "segment": m["seg"], "image": "",
             "imageSource": m["img"], "lowPrice": min(t["price"] for v in variants for t in v["trims"]), "priceDate": None,
             "sources": [BASE] + m["src"][:3], "structure": "price-list", "variants": variants,
             "notes": ["포르쉐코리아 공식 홈페이지의 모델 버전별 권장 가격과 제원입니다. 포르쉐는 대부분의 장비를 개별 옵션으로 선택합니다."]}
        save(out / f"{slug}.json", d)
        print(d["id"], [(v["name"], [(t["name"], t["price"]) for t in v["trims"]]) for v in variants])


if __name__ == "__main__":
    main()
