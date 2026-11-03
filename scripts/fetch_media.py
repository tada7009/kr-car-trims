"""차종별 고해상도 외관·실내 사진을 제조사 공식 페이지에서 모아 img/에 저장한다.

- 대표 외관: 배경이 투명한 고해상도 렌더(가로 800px 이상)가 있으면 그것, 없으면 고해상도 외관 사진(현대처럼)
- 실내: 공식 갤러리·디자인 사진 중 가로 1000px 이상을 최대 3장
결과는 data/<brand>/*.json의 media = {hero, heroType: cut|photo, ext: [...], int: [...]} 로 기록한다.
목록용 작은 썸네일(image)은 fetch_images.py가 만든 것을 그대로 둔다.
"""
import io
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

from common import DATA, ROOT

IMG = ROOT / "img"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130"}
INT = re.compile(r"interior|gal-int|_int[_.\-]|-int-|inside|cockpit|indoor|seat|cabin", re.I)
EXT_PHOTO = re.compile(r"gallery_exterior|gal-ext|exterior_main|design-ext|gallery/exterior|_kv|carousel|exterior", re.I)
EXT_CUT = re.compile(r"colorizer|represent|builder/car_img|main_off|MODEL_|bto-exterior|well-side|45side|car_img", re.I)
SKIP = re.compile(r"icon|logo|btn|banner_s|thumb|_mo[._]|mobile|swatch|chip|badge|/m/|-mo\.|_m\.", re.I)
CHEVY = {"chevrolet-trailblazer": "https://www.chevrolet.co.kr/suvs/trailblazer",
         "chevrolet-trax-crossover": "https://www.chevrolet.co.kr/cuvs/trax-crossover"}
RENAULT = {"renault-arkana": "arkana", "renault-grand-koleos": "koleos", "renault-filante": "filante"}


def get(url, timeout=40):
    with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=timeout) as r:
        return r.read()


def text(url):
    try:
        return get(url).decode("utf-8", "replace")
    except Exception:
        return ""


def urls_in(html, base):
    found = re.findall(r'(https?://[^"\'\s()<>]+?\.(?:jpg|jpeg|png|webp))', html)
    found += ["https:" + u for u in re.findall(r'["\'(](//[a-z0-9.-]+\.[a-z]{2,}/[^"\'\s()<>]+?\.(?:jpg|jpeg|png|webp))', html)]
    found += [base + u for u in re.findall(r'["\'(](/(?:static|content|contents|attached|upload|wstatic|wcontents|ko/resource)[^"\'\s()<>]+?\.(?:jpg|jpeg|png|webp))', html)]
    return list(dict.fromkeys(u for u in found if not SKIP.search(u)))


def sources(d):
    """차종 → (후보 이미지 주소 목록, 이미 정해진 투명 렌더 주소)"""
    mid, brand = d["id"], d["brand"]
    cands, cut = [], d.get("imageSource")
    if brand == "hyundai" and "casper" in mid:
        page = "https://casper.hyundai.com/vehicles/" + ("electric/highlight" if "electric" in mid else "highlight")
        cands = urls_in(text(page), "https://casper.hyundai.com")
    elif brand == "hyundai":
        api = "https://www.hyundai.com/kr/ko/gw/product/v1/product/car-detailpage/{0}/H?repnCarCode={0}&siteSnCode=H"
        for code in dict.fromkeys(v["code"] for v in d["variants"]):
            try:
                info = json.loads(get(api.format(code)))["data"][0]
            except Exception:
                continue
            for u in info.get("usfList") or []:
                if u.get("menuTypeCode") == "01":
                    cands += urls_in(text(f"https://www.hyundai.com{u['urlAdr']}/{u['fileNm']}"), "https://www.hyundai.com")
            if cands:
                break
    elif brand == "kia":
        slug = d["variants"][0]["code"]
        cands = urls_in(text(f"https://www.kia.com/kr/vehicles/{slug}"), "https://www.kia.com")
    elif brand == "genesis":
        api = "https://www.genesis.com/wsvc/kr/api/v2/structure/data?key=btomodel&lngloc=ko-KR&model="
        try:
            j = json.loads(get(api + d["variants"][0]["code"]))
            first = j["exteriorColors"][0]["list"][0]["image"]
            cut = "https://www.genesis.com" + first["large"]
            for des in j.get("interiorDesigns") or []:
                for c in des.get("interiorColors") or []:
                    im = c.get("image") or {}
                    if isinstance(im, dict) and im.get("large"):
                        cands.append("https://www.genesis.com" + im["large"])
        except Exception:
            pass
    elif brand == "kgm":
        plp = json.loads(get("https://web.kg-mobility.com/app/display/getPlpModelList.do"))
        codes = {v["code"] for v in d["variants"]}
        disp = []

        def walk(o):
            if isinstance(o, dict):
                if o.get("modelCd") in codes and o.get("dispCatNo"):
                    disp.append(o["dispCatNo"])
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(plp)
        for no in disp[:1]:
            body = json.loads(get(f"https://web.kg-mobility.com/app/display/getCarDetailContents.do?dispCatNo={no}"))["body"]
            # 실내 영역의 사진 중 제목이 실내·시트·콕핏인 것을 앞에, 트렁크·적재 공간은 뺀다
            found = []

            def walk_int(o):
                if isinstance(o, dict):
                    u, t = o.get("imgUrl") or "", (o.get("title") or "") + (o.get("subTitle") or "")
                    if re.search(r"\.(jpg|jpeg|png|webp)$", u, re.I) and not re.search(r"트렁크|러기지|적재|트레이", t):
                        found.append((0 if re.search(r"COCKPIT|콕핏|실내|인테리어|시트|공간|대시|디스플레이", t, re.I) else 1, u))
                    for v in o.values():
                        walk_int(v)
                elif isinstance(o, list):
                    for v in o:
                        walk_int(v)
            walk_int(body.get("interior") or {})
            cands += [u + "#int" for _, u in sorted(found, key=lambda x: x[0])]
            s = json.dumps(body.get("exterior") or {}, ensure_ascii=False)
            cands += [u + "#ext" for u in re.findall(r'https?://[^"\s]+?\.(?:jpg|jpeg|png|webp)', s)][:6]
    elif brand == "renault":
        cands = urls_in(text(f"https://www.renault.co.kr/ko/model/{RENAULT[mid]}_overview.jsp"), "https://cdn.renault.co.kr")
    elif brand == "chevrolet":
        cands = urls_in(text(CHEVY[mid]), "https://www.chevrolet.co.kr")
    return cands, cut


def probe(url):
    try:
        im = Image.open(io.BytesIO(get(url.split("#")[0], 30)))
        im.load()
    except Exception:
        return None
    alpha = None
    if im.mode in ("RGBA", "LA", "P"):
        a = im.convert("RGBA").getchannel("A")
        box = a.getbbox()
        if box and a.getextrema()[0] < 250:
            alpha = (box[2] - box[0]) * (box[3] - box[1]) / (im.width * im.height)
    return {"url": url, "im": im, "w": im.width, "h": im.height, "alpha": alpha}


def pick(d):
    cands, cut = sources(d)
    pri = lambda u: (0 if "#int" in u or INT.search(u) else 1 if EXT_PHOTO.search(u) or "#ext" in u else 2 if EXT_CUT.search(u) else 3)
    cands = sorted(dict.fromkeys(cands), key=pri)
    # 제네시스 실내 사진은 불투명 PNG로 올라와 있어 PNG도 받는다(투명 여부는 아래에서 거른다)
    ints = [u for u in cands if ("#int" in u or INT.search(u)) and (d["brand"] == "genesis" or not re.search(r"\.png", u))][:12]
    exts = [u for u in cands if ("#ext" in u or EXT_PHOTO.search(u)) and u not in ints][:8]
    cuts = ([cut] if cut else []) + [u for u in cands if EXT_CUT.search(u) and u != cut][:6]
    with ThreadPoolExecutor(8) as ex:
        P = {u: r for u, r in zip(ints + exts + cuts, ex.map(probe, ints + exts + cuts)) if r}
    hero_cut = max((P[u] for u in cuts if u in P and P[u]["alpha"] and P[u]["alpha"] < 0.92 and P[u]["w"] >= 800),
                   key=lambda r: r["w"], default=None)
    photos = [P[u] for u in exts if u in P and not P[u]["alpha"] and P[u]["w"] >= 1200 and P[u]["w"] > P[u]["h"]]
    if not hero_cut and not photos:  # 이름 규칙에 안 맞아도 큰 가로 사진이면 대표 사진으로 쓴다(캐스퍼 일렉트릭 등)
        rest = [u for u in cands if u not in P][:20]
        with ThreadPoolExecutor(8) as ex:
            extra = [r for r in ex.map(probe, rest) if r]
        photos = sorted([r for r in extra if not r["alpha"] and r["w"] >= 1000 and r["w"] > r["h"] * 1.4],
                        key=lambda r: -r["w"])[:1]
    stem = lambda u: re.sub(r"[_-]?(pc|mo|lg|sm|\d{1,2})?\.\w+$", "", u.split("/")[-1])
    inner = []
    for min_w in (900, 640):  # 고해상도가 없을 때만 640px 이상으로 내려 받는다
        for u in ints:
            r = P.get(u)
            if r and r not in inner and not r["alpha"] and r["w"] >= min_w and r["w"] >= r["h"]:
                if all(stem(x["url"]) != stem(u) or "gallery" in u for x in inner):
                    inner.append(r)
            if len(inner) == 3:
                break
        if inner:
            break
    return hero_cut, photos[:2], inner


def save(im, path, cut=False, width=1600, q=80):
    im = im.convert("RGBA" if cut else "RGB")
    if cut:
        box = im.getchannel("A").getbbox()
        if box:
            im = im.crop((max(box[0] - 8, 0), max(box[1] - 8, 0), min(box[2] + 8, im.width), min(box[3] + 8, im.height)))
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(path, "WEBP", quality=q, method=6)
    return im.size


def process(fd):
    f, d = fd
    try:
        cut, photos, inner = pick(d)
    except Exception as e:
        return d["id"], f"error {e}"
    mid = d["id"]
    media = {"ext": [], "int": []}
    if cut:
        save(cut["im"], IMG / f"{mid}.webp", cut=True, width=1400, q=86)
        d["imageSource"] = cut["url"].split("#")[0]
        media.update(hero=f"img/{mid}.webp", heroType="cut")
    for i, p in enumerate(photos, 1):
        save(p["im"], IMG / f"{mid}-x{i}.webp")
        media["ext"].append(f"img/{mid}-x{i}.webp")
    if not cut and media["ext"]:
        media.update(hero=media["ext"][0], heroType="photo")
    for i, p in enumerate(inner, 1):
        save(p["im"], IMG / f"{mid}-i{i}.webp", q=78)
        media["int"].append(f"img/{mid}-i{i}.webp")
    if "hero" not in media:
        media.update(hero=d.get("image", ""), heroType="cut")
    d["media"] = media
    f.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return mid, f"hero={media['heroType']}{' ' + str(cut['w']) if cut else ''} ext={len(media['ext'])} int={len(media['int'])}"


def main(only=None):
    IMG.mkdir(exist_ok=True)
    files = [f for f in sorted(DATA.glob("*/*.json"))]
    models = [(f, json.loads(f.read_text(encoding="utf-8"))) for f in files]
    models = [(f, d) for f, d in models if not only or d["id"] in only]
    with ThreadPoolExecutor(4) as ex:
        for mid, msg in ex.map(process, models):
            print(mid, msg)


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
