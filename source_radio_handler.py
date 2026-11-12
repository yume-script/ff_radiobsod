import hashlib
import json
import os
import re
import traceback
from urllib.parse import urljoin

from flask import Response, redirect, jsonify

from .setup import P, F

REGIONS = ["수도권", "부산·울산·경남", "대구·경북", "광주·전남", "전북",
           "대전·세종·충남", "충북", "강원", "제주"]
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/124 Safari/537.36"}
URL_RE = re.compile(r"""https?://[^\s"'`\\<>)]+""")
STREAM_HINT = re.compile(r"(\.m3u8|\.aac|\.mp3|\.pls|/live|/radio|stream|icecast|hls|:\d{4}/)", re.I)
SKIP_HOST = re.compile(r"(github\.com|googleapis|gstatic|cloudflare|w3\.org|fonts\.)", re.I)


class RadioHandler:
    # ------------------------------------------------------------ cache
    @classmethod
    def cache_path(cls):
        return os.path.join(F.config["path_data"], "db", f"{P.package_name}_channels.json")

    @classmethod
    def load(cls):
        try:
            with open(cls.cache_path(), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    @classmethod
    def save(cls, rows):
        with open(cls.cache_path(), "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------ scrape
    @classmethod
    def _fetch(cls, url):
        headers = dict(UA)
        headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": "https://radio.bsod.kr/",
        })
        # 1) curl_cffi (크롬 TLS 지문 위장) - 설치돼 있을 때 우선 사용
        try:
            from curl_cffi import requests as cr
            r = cr.get(url, headers=headers, impersonate="chrome", timeout=20)
            if r.status_code == 200:
                r.encoding = "utf-8"
                return r.text
            P.logger.warning(f"curl_cffi {r.status_code}: {url}")
        except ImportError:
            pass
        except Exception as e:
            P.logger.warning(f"curl_cffi error: {e}")
        # 2) 일반 requests
        import requests
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 403:
            # 3) cloudscraper 가 있으면 시도
            try:
                import cloudscraper
                r = cloudscraper.create_scraper().get(url, headers=headers, timeout=20)
            except ImportError:
                pass
        if r.status_code != 200:
            raise Exception(f"HTTP {r.status_code}: {url} (pip install curl_cffi 후 재시도하거나, 설정의 '로컬 소스 경로'를 사용하세요)")
        r.encoding = "utf-8"
        return r.text

    @classmethod
    def _sources(cls, base):
        local = (P.ModelSetting.get("source_file") or "").strip()
        if local:
            out = {}
            paths = []
            if os.path.isdir(local):
                for fn in sorted(os.listdir(local)):
                    if fn.lower().endswith((".html", ".htm", ".js", ".json", ".txt")):
                        paths.append(os.path.join(local, fn))
            elif os.path.exists(local):
                paths.append(local)
            for fp in paths:
                with open(fp, encoding="utf-8", errors="ignore") as f:
                    out[fp] = f.read()
            if not out:
                raise Exception(f"로컬 소스 경로에 읽을 파일이 없음: {local}")
            return out
        html = cls._fetch(base)
        out = {base: html}
        for ref in re.findall(r'(?:src|href)=["\']([^"\']+\.(?:js|json)(?:\?[^"\']*)?)["\']', html):
            u = urljoin(base, ref)
            if u in out or SKIP_HOST.search(u):
                continue
            try:
                out[u] = cls._fetch(u)
            except Exception as e:
                P.logger.warning(f"skip {u}: {e}")
        return out

    @classmethod
    def _walk_json(cls, node, region="", out=None):
        out = [] if out is None else out
        if isinstance(node, dict):
            url = next((v for k, v in node.items()
                        if isinstance(v, str) and v.startswith("http")
                        and k.lower() in ("url", "stream", "streamurl", "src", "link")), None)
            if url:
                out.append({"region": region, "name": node.get("name") or node.get("title") or "", "url": url})
            for k, v in node.items():
                cls._walk_json(v, k if k in REGIONS else region, out)
        elif isinstance(node, list):
            for v in node:
                cls._walk_json(v, region, out)
        return out

    @classmethod
    def _guess(cls, text, pos):
        """URL 앞뒤 문맥에서 (지역, 채널명) 추정. 실제 사이트 구조 확인 후 교체 권장."""
        ctx = text[max(0, pos - 250):pos + 250]
        m = re.search(r'(?:name|title|label|channel)["\']?\s*[:=]\s*["\']([^"\']+)["\']', ctx, re.I)
        name = m.group(1) if m else ""
        before = text[:pos]
        region = ""
        last = -1
        for r in REGIONS:
            i = before.rfind(r)
            if i > last:
                last, region = i, r
        return region, name

    @classmethod
    def scrape(cls):
        base = P.ModelSetting.get("source_url") or "https://radio.bsod.kr/"
        sources = cls._sources(base)
        rows = []
        for u, body in sources.items():
            if u.endswith(".json"):
                try:
                    rows += cls._walk_json(json.loads(body))
                    continue
                except Exception:
                    pass
            for m in URL_RE.finditer(body):
                url = m.group(0).rstrip(",;")
                if SKIP_HOST.search(url) or not STREAM_HINT.search(url):
                    continue
                region, name = cls._guess(body, m.start())
                rows.append({"region": region, "name": name, "url": url})
        if not rows:
            P.logger.warning("스트림 URL을 찾지 못함: 사이트 구조 확인 후 _guess/scrape 수정 필요")
        return rows

    @classmethod
    def sync(cls):
        rows = cls.scrape()
        uniq = {}
        for r in rows:
            key = (r["region"], r["name"], r["url"])
            r["id"] = hashlib.sha1("|".join(key).encode()).hexdigest()[:10]
            uniq[key] = r
        rows = list(uniq.values())
        cls.save(rows)
        P.logger.info(f"채널 {len(rows)}개 저장")
        return len(rows)

    # ------------------------------------------------------------ views
    @classmethod
    def ch_list(cls):
        rows = cls.load()
        if not rows:
            cls.sync()
            rows = cls.load()
        flt = [x.strip() for x in (P.ModelSetting.get("region_filter") or "").split(",") if x.strip()]
        return [r for r in rows if not flt or r["region"] in flt]

    @classmethod
    def make_m3u(cls):
        from tool import ToolUtil
        direct = P.ModelSetting.get("m3u_url_type") == "direct"
        lines = ["#EXTM3U"]
        for r in cls.ch_list():
            url = r["url"] if direct else ToolUtil.make_apikey_url(f"/{P.package_name}/api/url?ch_id={r['id']}")
            lines.append(f'#EXTINF:-1 tvg-id="{r["id"]}" tvg-name="{r["name"]}" group-title="{r["region"]}",{r["name"]}')
            lines.append(url)
        return Response("\n".join(lines) + "\n", headers={"Content-Type": "audio/x-mpegurl; charset=utf-8"})

    @classmethod
    def url(cls, req):
        ch_id = req.args.get("ch_id")
        for r in cls.load():
            if r["id"] == ch_id:
                return redirect(r["url"])
        return jsonify({"ret": "error", "msg": "channel not found"})
