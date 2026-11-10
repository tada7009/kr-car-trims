"""수입차 차종 사진을 공식 자료에서 받아 img/에 저장하고 data/<brand>/*.json의 image·media를 채운다.

- BMW: 공식 모델 라인업 페이지의 배경 없는 렌더(cosy) — 주소 목록은 브라우저에서 모아 raw/bmw/cosy.json에 둔다
- 벤츠: 공식 구성기(owcc) 차종별 시작 화면의 미리보기 렌더(배경 투명), 구성기에 없는 차종은 모델 페이지 og:image
- 볼보: 공식 '나만의 볼보 디자인' 페이지의 스튜디오 렌더(배경 투명, 3/4 앞모습)
- 테슬라: 공식 모델 소개 페이지의 대표 사진(배경 있음) — 목록용 작은 사진은 가운데를 잘라 만든다
"""
import hashlib
import io
import json
import re
import sys
from pathlib import Path

from PIL import Image

from common import DATA, ROOT, curl_get

IMG = ROOT / "img"
RAW = Path(__file__).resolve().parent / "raw"
TESLA = {
    "tesla-model-3": ["Model-3-Premium-Hero-LHD-Desktop-APAC.jpg", "Model-3-Performance-Hero-LHD-Desktop-APAC.jpg"],
    "tesla-model-y": ["Model-Y-Premium-Hero-Localized-Desktop-KR.jpg", "Model-Y-L-End-Desktop-LHD.jpg"],
    "tesla-cybertruck": ["Cybertruck-Hero-Desktop-NA-SA-APAC.png"],
}
TESLA_BASE = "https://digitalassets.tesla.com/tesla-contents/image/upload/f_auto,q_auto/"
BMW = {  # 모델 id → 라인업 페이지 이미지의 alt
    "1-series-hatch": "BMW 120", "2-series-coupe": "BMW M240i xDrive 쿠페", "2-series-active-tourer": "BMW 220i 액티브 투어러",
    "2-series-gran-coupe": "BMW 220", "3-series-sedan": "BMW 320i", "3-series-touring": "BMW 320i 투어링",
    "4-series-coupe": "BMW 420i 쿠페", "4-series-convertible": "BMW 420i 컨버터블", "4-series-gran-coupe": "BMW 420i 그란 쿠페",
    "5-series-sedan": "BMW 530i xDrive", "7-series-sedan": "740 xDrive", "8-series-gran-coupe": "BMW M850i xDrive 그란 쿠페",
    "ix": "BMW iX xDrive60", "i5": "BMW i5 eDrive40", "ix1": "BMW iX1 eDrive20", "ix2": "BMW iX2 eDrive20", "i7": "i7 50 xDrive",
    "ix3": "BMW iX3 50 xDrive", "i4": "BMW i4 eDrive40 그란 쿠페", "x1": "BMW X1 xDrive20i", "x2": "BMW X2 xDrive20i",
    "x3": "BMW X3 20 xDrive", "x4": "BMW X4 xDrive20i", "x5": "BMW X5 xDrive40i", "x6": "BMW X6 xDrive40i",
    "x7": "BMW X7 xDrive40i", "xm": "BMW XM 레이블", "z4": "BMW Z4 sDrive20i 로드스터", "m2": "BMW M2 쿠페",
    "m3": "BMW M3 컴페티션 M xDrive", "m4": "BMW M4 컴페티션 M xDrive 쿠페", "m5": "BMW M5",
}
MB_CLASS = [  # 모델 이름(AMG·Maybach 앞머리 뺀 것) → 구성기 typeClass
    ("A-Class", "W177"), ("CLA", "C178"), ("GT 4-Door", None), ("GT", "C192"), ("E-Class", "W214"), ("S-Class", "W223"),
    ("SL", "R232"), ("CLE Coupé", "C236"), ("CLE Cabriolet", "A236"), ("GLB", "X247"), ("GLA", "H247"),
    ("GLC Coupé", "C254"), ("GLC", "X254"), ("GLE Coupé", "C167"), ("GLE", "V167"), ("GLS", "X167"),
    ("EQS SUV", "X296"), ("G-Class", "W465"),
]
MB_PAGE = {"C-Class": "saloon/c-class", "EQE": "saloon/eqe", "EQA": "suv/eqa", "EQB": "suv/eqb", "EQE SUV": "suv/eqe",
           "GT 4-Door": "coupe/amg-gt"}
MB_API = "https://api.oneweb.mercedes-benz.com/owcc-backend/api/v3/ko_KR/CCci"
MB_H = {"Origin": "https://www.mercedes-benz.co.kr", "Referer": "https://www.mercedes-benz.co.kr/", "Accept": "application/json"}


def load(url):
    im = Image.open(io.BytesIO(curl_get(url, binary=True)))
    im.load()
    return im


def save(im, name, cut, width):
    im = im.convert("RGBA" if cut else "RGB")
    if cut:  # 옅은 그림자까지 넣으면 차가 작아져서, 어느 정도 불투명한 부분 기준으로 자른다
        box = im.getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox()
        if box:
            im = im.crop((max(box[0] - 8, 0), max(box[1] - 8, 0), min(box[2] + 8, im.width), min(box[3] + 8, im.height)))
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    path = IMG / name
    im.save(path, "WEBP", quality=86 if cut else 80, method=6)
    return f"img/{name}?{hashlib.md5(path.read_bytes()).hexdigest()[:8]}"


def has_alpha(im):
    return im.mode in ("RGBA", "LA", "P") and im.convert("RGBA").getchannel("A").getextrema()[0] < 250


def drop_black(im):
    """BMW 렌더 일부는 투명 대신 검은 배경 JPEG로 내려온다. 테두리에서 이어진 검은 영역만 투명하게 만든다."""
    from PIL import ImageDraw
    rgb = im.convert("RGB")
    # 배경은 완전한 검정(0)이고 타이어·그늘은 그보다 밝아서, 거의 0인 곳만 배경으로 본다
    dark = rgb.convert("L").point(lambda v: 255 if v < 3 else 0)
    for xy in ((0, 0), (dark.width - 1, 0), (0, dark.height - 1), (dark.width - 1, dark.height - 1)):
        if dark.getpixel(xy) == 255:
            ImageDraw.floodfill(dark, xy, 128)
    alpha = dark.point(lambda v: 0 if v == 128 else 255)
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def cut_from(d, url, black_bg=False):
    im = load(url)
    if black_bg and not has_alpha(im) and im.convert("L").getpixel((0, 0)) < 3:
        im = drop_black(im)
    if not has_alpha(im):
        return None
    p = save(im, f"{d['id']}.webp", True, 1400)
    return {"image": p, "media": {"hero": p, "heroType": "cut", "ext": [], "int": []}, "src": url}


def tesla(d):
    files = TESLA.get(d["id"], [])
    ext = []
    for i, f in enumerate(files, 1):
        im = load(TESLA_BASE + f)
        ext.append(save(im, f"{d['id']}-x{i}.webp", False, 1600))
        if i == 1:  # 목록용: 가운데를 16:9로 잘라 작게
            im = im.convert("RGB")
            h = min(im.height, round(im.width * 9 / 16))
            w = round(h * 16 / 9)
            im = im.crop(((im.width - w) // 2, (im.height - h) // 2, (im.width + w) // 2, (im.height + h) // 2))
            thumb = save(im, f"{d['id']}.webp", False, 960)
    if not ext:
        return None
    return {"image": thumb, "media": {"hero": ext[0], "heroType": "photo", "ext": ext, "int": []}, "src": TESLA_BASE + files[0]}


def bmw(d, cosy):
    alt = BMW.get(d["id"][4:])
    for u in (cosy.get(alt) or []):
        r = cut_from(d, u, black_bg=True)
        if r:
            return r
    return None


_mb_version = None


def mercedes(d):
    global _mb_version
    base = re.sub(r"^(AMG|Maybach) ", "", d["name"])
    tc = next((t for n, t in MB_CLASS if base == n or base.startswith(n + " ") and n != "GT"), None)
    if base == "GT":
        tc = "C192"
    if tc:
        if not _mb_version:
            _mb_version = json.loads(curl_get(f"{MB_API}/version", cache=False, headers=MB_H))
            _mb_version = _mb_version.get("version") or _mb_version.get("dataVersion") or _mb_version
        ver = _mb_version if isinstance(_mb_version, (str, int)) else "56644576"
        try:
            entry = json.loads(curl_get(f"{MB_API}/{ver}/entry?typeClass={tc}", headers=MB_H))
        except Exception:
            entry = {}
        pcs = (entry.get("startPage") or {}).get("preConfigs") or []
        want = "AMG" if d["name"].startswith("AMG") else "MAYBACH" if d["name"].startswith("Maybach") else "MB"
        pcs = sorted(pcs, key=lambda p: 0 if want in (p.get("labels") or []) else 1)
        for p in pcs:
            u = (p.get("previewImage") or {}).get("url")
            if u:
                r = cut_from(d, u)
                if r:
                    return r
    page = MB_PAGE.get(base)
    if page:
        try:
            html = curl_get(f"https://www.mercedes-benz.co.kr/passengercars/models/{page}/overview.html")
            m = re.search(r'property="og:image" content="([^"]+)"', html)
            if m:  # 배경 투명이 아니면 사진으로 쓴다
                return cut_from(d, m.group(1)) or photo_set(d, [m.group(1)])
        except Exception:
            return None
    return None


def volvo(d):
    for v in d["variants"]:
        html = curl_get(f"https://www.volvocars.com/kr/build/{v['code']}/")
        m = re.search(r'(https://wizz\.volvocars\.com/images/[^"\s?]*threeQuartersFrontLeft[^"\s?]*\.png)', html)
        if m:
            r = cut_from(d, m.group(1) + "?client=pdps&w=1920")
            if r:
                return r
        m = re.search(r'(https://cas\.volvocars\.com/image/dynamic/[^"\s?]*/default\.png)', html)  # 이전 세대 구성기 렌더
        if m:  # market 값이 없으면 400, bg=00000000이면 배경 투명, angle=4가 3/4 앞모습(왼쪽)
            r = cut_from(d, m.group(1) + "?market=kr&client=ccs-self-service&angle=4&w=1920&bg=00000000")
            if r:
                return r
    return None


def photo_set(d, urls):
    """배경 있는 공식 사진 여러 장 → 외관 사진(x1, x2…)과 가운데를 자른 목록용 사진"""
    ext, thumb = [], None
    for i, u in enumerate(urls, 1):
        im = load(u)
        ext.append(save(im, f"{d['id']}-x{i}.webp", False, 1600))
        if i == 1:
            im = im.convert("RGB")
            h = min(im.height, round(im.width * 9 / 16))
            w = round(h * 16 / 9)
            thumb = save(im.crop(((im.width - w) // 2, (im.height - h) // 2, (im.width + w) // 2, (im.height + h) // 2)),
                         f"{d['id']}.webp", False, 960)
    if not ext:
        return None
    return {"image": thumb, "media": {"hero": ext[0], "heroType": "photo", "ext": ext, "int": []}, "src": urls[0]}


_lexus_imgs = None


def lexus(d):
    """렉서스: 모델 검색 데이터의 옆모습 렌더(배경 투명)"""
    global _lexus_imgs
    if _lexus_imgs is None:
        ms = curl_get("https://www.lexus.co.kr/data/json/getData-model-search.php", cache=False)
        _lexus_imgs = {k: s.replace("\\/", "/") for k, s in re.findall(r'"key":"([^"]+)".*?"desktop":\{"src":"([^"]+)"', ms)}
    for v in d["variants"]:
        key = v["code"].replace("vip", "")
        src = _lexus_imgs.get(key) or _lexus_imgs.get(v["code"])
        if src:
            r = cut_from(d, "https://www.lexus.co.kr" + src.replace(" ", "%20"))
            if r:
                return r
    return None


TOYOTA_THUMB = {"rav4hev": "rav4-hev-limited", "rav4phev": "rav4-phev-xse"}


def toyota(d):
    """토요타: 모델 검색 목록의 옆모습 렌더(배경 투명) → 없으면 모델 페이지의 외관 사진"""
    for v in d["variants"]:
        key = TOYOTA_THUMB.get(v["code"], v["code"])
        try:
            r = cut_from(d, f"https://www.toyota.co.kr/assets/img/model/thumbnail/thumbnail-{key}.webp")
            if r:
                return r
        except Exception:
            pass
    for v in d["variants"]:
        html = curl_get(f"https://www.toyota.co.kr/models/{v['code']}/")
        urls = sorted(set(re.findall(r'(/assets/img/model/[^"\'\s]*?-exterior-\d\.webp)', html)))[:2]
        if urls:
            return photo_set(d, ["https://www.toyota.co.kr" + u for u in urls])
    return None


def audi(d):
    """아우디: 모델 목록의 차량 렌더(배경 투명, raw/audi/images.json) → 없으면 모델 페이지 대표 사진"""
    imgs = json.loads((RAW / "audi" / "images.json").read_text(encoding="utf-8"))
    key = {"RS 3": "A3", "RS Q8": "Q8"}.get(d["name"], d["name"])
    if f"Audi {key}" in imgs:
        r = cut_from(d, imgs[f"Audi {key}"])
        if r:
            return r
    html = curl_get(d["sources"][0])
    found = list(dict.fromkeys(re.findall(r'(https://emea-dam\.audi\.com/adobe/assets/urn:aaid:aem:[0-9a-f-]+/as/[^"&\s]+?\.jpg)', html)))
    pc = [u for u in found if "_PC_" in u] + [u for u in found if u.endswith("-L.jpg")]  # 데스크톱 대표 사진 → 큰 갤러리 사진
    return photo_set(d, pc[:2]) if pc else None


def porsche(d):
    """포르쉐: 트림 페이지 구조화 데이터의 옆모습 렌더(scrape_porsche.py가 imageSource에 적어 둔다)"""
    u = d.get("imageSource")
    if not u:
        return None
    return cut_from(d, u) or photo_set(d, [u])


# 폭스바겐 가격표 PDF에 들어 있는 공식 사진(PDF 안 이미지 번호 xref): (외관들, 실내들). 첫 외관이 대표 사진
VW_PICK = {
    "volkswagen-atlas": ([876, 95, 97], [878]),
    "volkswagen-golf-gti": ([51, 1038, 53], [1040]),
    "volkswagen-golf": ([905, 67], [907]),
    "volkswagen-id-4": ([939, 41], [937]),
    "volkswagen-id-5": ([35, 33, 965], [967]),
    "volkswagen-touareg": ([1375, 61], [1373]),
}


def volkswagen(d):
    """폭스바겐: 이미지 서버(assets.volkswagen.com)·사이트 사진은 자동 요청이 막혀(403/410),
    모델 페이지에 걸린 공식 가격표 PDF 안의 사진을 꺼내 쓴다. 가격표가 바뀌어 번호가 없으면 가로 사진 중 큰 것."""
    import fitz
    pdf = next((s for s in d["sources"] if s.lower().endswith(".pdf")), None)
    if not pdf:
        return None
    doc = fitz.open(stream=curl_get(pdf, binary=True), filetype="pdf")
    imgs = {}
    for pn, page in enumerate(doc):
        for it in page.get_images(full=True):
            x = doc.extract_image(it[0])
            if x["width"] * x["height"] >= 1_000_000:
                imgs[it[0]] = (pn, x)
    ext_ids, int_ids = VW_PICK.get(d["id"], ([], []))
    if not all(i in imgs for i in ext_ids):  # 가격표가 새로 나와 번호가 바뀐 경우
        land = sorted((k for k, (pn, x) in imgs.items() if pn > 0 and x["width"] > x["height"] * 1.2),
                      key=lambda k: -imgs[k][1]["width"] * imgs[k][1]["height"])
        ext_ids, int_ids = land[:2], []
    if not ext_ids:
        return None

    def pil(i):
        im = Image.open(io.BytesIO(imgs[i][1]["image"]))
        im.load()
        return im.convert("RGB")

    ext = [save(pil(i), f"{d['id']}-x{n}.webp", False, 1600) for n, i in enumerate(ext_ids, 1)]
    inn = [save(pil(i), f"{d['id']}-i{n}.webp", False, 1600) for n, i in enumerate(int_ids, 1) if i in imgs]
    im = pil(ext_ids[0])
    h = min(im.height, round(im.width * 9 / 16))
    w = round(h * 16 / 9)
    thumb = save(im.crop(((im.width - w) // 2, (im.height - h) // 2, (im.width + w) // 2, (im.height + h) // 2)),
                 f"{d['id']}.webp", False, 960)
    return {"image": thumb, "media": {"hero": ext[0], "heroType": "photo", "ext": ext, "int": inn}, "src": pdf}


def polestar(d):
    """폴스타: 모델 소개 페이지의 대표 이미지(og:image)"""
    html = curl_get(f"https://www.polestar.com/kr/{d['variants'][0]['code']}/")
    m = re.search(r'<meta[^>]+og:image[^>]+content="([^"]+)"', html)
    if not m:
        return None
    return cut_from(d, m.group(1)) or photo_set(d, [m.group(1)])


LANDROVER = {  # 모델 id → 공식 사이트 사진(jlr.scene7.com) — 사양 페이지 렌더는 흰 배경 640px이라 배경 있는 사진을 쓴다
    "landrover-defender": ["L66326GL_303104383_060", "L66326GL_303104383_045", "L66326GL_303104383_073"],
    "landrover-discovery": ["L46226GL_303104584_005"],
    "landrover-discovery-sport": ["L55026GL_303104697_014", "L55026GL_303104697_001_HERO"],
    "landrover-range-rover": ["L460_22MY_117_GLHD_DX_Crop"],
    "landrover-range-rover-sport": ["L461_23MY_003_GLHD_SANTORINI_BLACK"],
    "landrover-range-rover-velar": ["L56026GL_303103980_001_NAV"],
    "landrover-range-rover-evoque": ["L55126GL_303103981_001"],
}


def landrover(d):
    """랜드로버: 국내 공식 사이트(차종 선택·모델 페이지)에 쓰인 Scene7 사진"""
    ids = LANDROVER.get(d["id"])
    return photo_set(d, [f"https://jlr.scene7.com/is/image/jlr/{i}?wid=1920&fmt=jpg" for i in ids]) if ids else None


def main(only=None):
    IMG.mkdir(exist_ok=True)
    cosy = json.loads((RAW / "bmw" / "cosy.json").read_text(encoding="utf-8"))
    for brand in ("tesla", "bmw", "mercedes", "volvo", "lexus", "toyota", "audi", "porsche", "volkswagen", "polestar", "landrover"):
        for f in sorted((DATA / brand).glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            if only and d["id"] not in only:
                continue
            try:
                r = {"tesla": tesla, "bmw": lambda x: bmw(x, cosy), "mercedes": mercedes, "volvo": volvo,
                     "lexus": lexus, "toyota": toyota, "audi": audi, "porsche": porsche,
                     "volkswagen": volkswagen, "polestar": polestar, "landrover": landrover}[brand](d)
            except Exception as e:
                print(d["id"], "error", e)
                continue
            if not r:
                print(d["id"], "NO IMAGE")
                continue
            d["image"], d["media"], d["imageSource"] = r["image"], r["media"], r["src"]
            f.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            print(d["id"], r["media"]["heroType"])


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
