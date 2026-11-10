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
MB_PAGE = {"C-Class": "saloon/c-class", "EQE": "saloon/eqe", "EQA": "suv/eqa", "EQB": "suv/eqb", "EQE SUV": "suv/eqe-suv",
           "GT 4-Door": "coupe/mercedes-amg-gt-4-door-coupe"}
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
            if m:
                return cut_from(d, m.group(1))
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
        if m:
            r = cut_from(d, m.group(1))
            if r:
                return r
    return None


def main(only=None):
    IMG.mkdir(exist_ok=True)
    cosy = json.loads((RAW / "bmw" / "cosy.json").read_text(encoding="utf-8"))
    for brand in ("tesla", "bmw", "mercedes", "volvo"):
        for f in sorted((DATA / brand).glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            if only and d["id"] not in only:
                continue
            try:
                r = {"tesla": tesla, "bmw": lambda x: bmw(x, cosy), "mercedes": mercedes, "volvo": volvo}[brand](d)
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
