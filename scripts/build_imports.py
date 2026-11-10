"""브라우저로 모아 둔 수입차 원자료(scripts/raw/<brand>/*.json) → data/<brand>/*.json

테슬라·볼보 공식 구성기는 파이썬으로 바로 받을 수 없어(봇 차단·화면에서만 그려짐) 내장 브라우저에서
트림·가격·사양을 추려 raw 폴더에 저장해 두고, 이 스크립트가 사이트 형식으로 바꾼다.
- 테슬라 raw: {eff, trims:[{name, price, cats, opts}]} (이미 사이트 형식에 가깝다)
- 볼보 raw: {slug, lv:[[레벨, 가격]], pt:[파워트레인], cats:[분류], rows:"분류번호|품목|레벨별 s·o·-"}
  s=기본, o=선택(가격 미공개), -=없음. 레벨 하나뿐인 모델(T8 등)은 그 레벨의 전체 기본 품목 목록이다.
"""
import hashlib
import json
import re
from datetime import date
from pathlib import Path

from common import DATA, save

RAW = Path(__file__).resolve().parent / "raw"

TESLA = {
    "model3": ("Model 3", "전기 세단", "https://www.tesla.com/ko_kr/model3/design"),
    "modely": ("Model Y", "전기 SUV", "https://www.tesla.com/ko_kr/modely/design"),
    "cybertruck": ("Cybertruck", "픽업", "https://www.tesla.com/ko_kr/cybertruck/design"),
}
VOLVO = {  # 모델 이름 → (차급, [원자료 slug…]) — 같은 차의 마일드 하이브리드와 T8을 한 모델의 변형으로 묶는다
    "XC40": ("SUV", ["xc40"]),
    "XC60": ("SUV", ["xc60", "xc60-hybrid"]),
    "XC90": ("SUV", ["xc90", "xc90-hybrid"]),
    "S90": ("세단", ["s90", "s90-hybrid"]),
    "V60 Cross Country": ("왜건", ["v60-cross-country"]),
    "EX30": ("전기 SUV", ["ex30-electric"]),
    "EX90": ("전기 SUV", ["ex90-electric"]),
    "ES90": ("전기 세단", ["es90-electric"]),
}


def code(s):
    return hashlib.md5(s.encode()).hexdigest()[:8]


def tesla():
    out = DATA / "tesla"
    out.mkdir(parents=True, exist_ok=True)
    for key, (name, seg, url) in TESLA.items():
        raw = json.loads((RAW / "tesla" / f"{key}.json").read_text(encoding="utf-8"))
        trims = []
        for t in raw["trims"]:
            cats = [{"cat": re.sub(r"\d+$", "", c["cat"]).strip(), "items": c["items"]} for c in t["cats"]]
            trims.append({"name": t["name"].strip(), "en": t.get("en", ""), "price": t["price"], "cats": cats,
                          "adds": [], "opts": t["opts"]})
        d = {"id": f"tesla-{key.replace('model', 'model-')}", "brand": "tesla", "name": name, "segment": seg,
             "image": "", "lowPrice": min(t["price"] for t in trims), "priceDate": raw["eff"][:10], "sources": [url],
             "structure": "configurator", "variants": [{"name": "전기", "code": key, "trims": trims}],
             "notes": ["테슬라 공식 홈페이지 '디자인하기' 화면의 차량 가격(보조금 적용 전)과 트림별 사양입니다. 색상·휠·FSD 등은 선택 옵션입니다."]}
        save(out / f"{key}.json", d)
        print(d["id"], len(trims), "트림")


def powertrain(s):
    s = re.sub(r"\s*(KRW [\d,]+|표준)$", "", s).strip()
    s = re.sub(r"\s*(사륜구동|후륜 구동|전륜 구동)$", "", s).strip()
    return s.replace("플러그-인", "플러그인")


def volvo():
    out = DATA / "volvo"
    out.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    for name, (seg, slugs) in VOLVO.items():
        variants, sources = [], []
        for slug in slugs:
            raw = json.loads((RAW / "volvo" / f"{slug}.json").read_text(encoding="utf-8"))
            sources.append(f"https://www.volvocars.com/kr/build/{slug}/")
            pts = raw["pt"]
            extra = []  # 추가 금액이 붙은 두 번째 파워트레인(ES90 Twin Motor)은 선택 옵션으로 둔다
            for p in pts[1:]:
                m = re.search(r"KRW ([\d,]+)", p)
                extra.append({"n": powertrain(p), "c": code(p), "p": int(m.group(1).replace(",", "")) if m else None,
                              "g": "파워트레인", **({} if m else {"ask": True})})
            rows = [r.split("|") for r in raw["rows"].split("\n") if r.count("|") >= 2]
            trims = []
            for li, (lname, price) in enumerate(raw["lv"]):
                cats, opts = {}, list(extra)
                for ci, item, st in rows:
                    s = st[li] if li < len(st) else st[-1]
                    cat = raw["cats"][int(ci)] if ci.lstrip("-").isdigit() and int(ci) >= 0 else "기타"
                    if s == "s":
                        cats.setdefault(cat, []).append({"n": item})
                    elif s == "o":
                        opts.append({"n": item, "c": code(item), "p": None, "g": cat, "ask": True})
                trims.append({"name": lname, "price": round(price / 1000) * 1000 if price else None,
                              "cats": [{"cat": c, "items": its} for c, its in cats.items()], "adds": [], "opts": opts})
            variants.append({"name": powertrain(pts[0]), "code": slug, "trims": trims})
        prices = [t["price"] for v in variants for t in v["trims"] if t["price"]]
        d = {"id": f"volvo-{name.lower().replace(' ', '-')}", "brand": "volvo", "name": name, "segment": seg,
             "image": "", "lowPrice": min(prices) if prices else None, "priceDate": today, "sources": sources,
             "structure": "configurator", "variants": variants,
             "notes": ["볼보코리아 공식 '나만의 볼보 디자인' 화면의 레벨별 가격과 장비 비교표입니다. 가격이 비어 있는 트림은 공식 사이트에 가격이 아직 공개되지 않은 것입니다.",
                       "선택 품목(○)은 가격이 공개되지 않아 '가격 별도'로 표시합니다."]}
        save(out / f"{d['id'][6:]}.json", d)
        print(d["id"], [(v["name"], [(t["name"], t["price"]) for t in v["trims"]]) for v in variants])


if __name__ == "__main__":
    tesla()
    volvo()
