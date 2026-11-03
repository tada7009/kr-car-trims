"""수집 스크립트 공통 도구: 캐시된 HTTP 요청, 텍스트 정리, JSON 저장."""
import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = Path(os.environ.get("CAR_CACHE", ROOT / ".cache"))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


def fetch(url, headers=None, cache=True, retries=3):
    """URL 본문을 문자열로 반환. 같은 URL은 캐시 폴더에서 다시 읽는다."""
    CACHE.mkdir(parents=True, exist_ok=True)
    url = urllib.parse.quote(url, safe=":/?&=%#,;+@!$'()*~[]")
    key = hashlib.sha1(url.encode()).hexdigest()
    path = CACHE / key
    if cache and path.exists():
        return path.read_text(encoding="utf-8")
    h = {"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}
    if headers:
        h.update(headers)
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=40) as r:
                raw = r.read()
                charset = r.headers.get_content_charset() or "utf-8"
            text = raw.decode(charset, errors="replace")
            path.write_text(text, encoding="utf-8")
            return text
        except Exception as e:  # 네트워크 오류는 잠시 쉬고 재시도
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"fetch failed: {url}: {last}")


def fetch_json(url, headers=None, cache=True):
    return json.loads(fetch(url, headers, cache))


def clean(s):
    """공백·HTML 엔티티 정리."""
    if s is None:
        return ""
    s = s.replace("\xa0", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip()


def won(s):
    """'1,200,000' 같은 금액 문자열 → 정수(원). 숫자가 없으면 None."""
    if s is None:
        return None
    d = re.sub(r"[^\d-]", "", str(s))
    return int(d) if d and d != "-" else None


def short(s, n=220):
    s = clean(s)
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
