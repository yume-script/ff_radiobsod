import json
import os
import time
import traceback

from flask import Response, redirect, jsonify

from .setup import P, F

UA = {"User-Agent": "Mozilla/5.0"}
CACHE_TTL = 300  # 서명 URL 캐시 시간(초)

# type: kbs  -> code = KBS 채널코드 (cfpwwwapi.kbs.co.kr ... /channel_code/{code})
#       mbc  -> code = sfm | mfm | chm (sminiplay.imbc.com/aacplay.ashx)
#       static -> url 고정 주소
DEFAULT_CHANNELS = [
    {"id": "kbs_21", "region": "수도권", "name": "KBS 1라디오", "type": "kbs", "code": "21"},
    {"id": "kbs_22", "region": "수도권", "name": "KBS 2라디오", "type": "kbs", "code": "22"},
    {"id": "kbs_23", "region": "수도권", "name": "KBS 3라디오", "type": "kbs", "code": "23"},
    {"id": "kbs_24", "region": "수도권", "name": "KBS 1FM", "type": "kbs", "code": "24"},
    {"id": "kbs_25", "region": "수도권", "name": "KBS 2FM", "type": "kbs", "code": "25"},
    {"id": "kbs_26", "region": "수도권", "name": "KBS 한민족방송", "type": "kbs", "code": "26"},
    {"id": "mbc_sfm", "region": "수도권", "name": "MBC 표준FM", "type": "mbc", "code": "sfm"},
    {"id": "mbc_mfm", "region": "수도권", "name": "MBC FM4U", "type": "mbc", "code": "mfm"},
    {"id": "mbc_chm", "region": "수도권", "name": "MBC mini 올댓뮤직", "type": "mbc", "code": "chm"},
    {"id": "ebs_iradio", "region": "수도권", "name": "EBS FM", "type": "static",
     "url": "https://ebsonair.ebs.co.kr/cloud1/iradio/playlist.m3u8"},
]

_cache = {}


class RadioHandler:
    # ------------------------------------------------------------ channels
    @classmethod
    def custom_path(cls):
        return os.path.join(F.config["path_data"], "db", f"{P.package_name}_custom_channels.json")

    @classmethod
    def channels(cls):
        """기본 채널 + 사용자 추가 채널(custom json, 같은 id면 덮어씀)."""
        chs = {c["id"]: dict(c) for c in DEFAULT_CHANNELS}
        try:
            if os.path.exists(cls.custom_path()):
                with open(cls.custom_path(), encoding="utf-8") as f:
                    for c in json.load(f):
                        if not c.get("name") or c.get("type") not in ("kbs", "mbc", "static"):
                            P.logger.warning(f"custom channel 무시: {c}")
                            continue
                        c.setdefault("region", "기타")
                        c.setdefault("id", f'{c["type"]}_{c.get("code") or abs(hash(c.get("url", "")))}')
                        chs[c["id"]] = c
        except Exception as e:
            P.logger.error(f"custom channels 읽기 실패: {e}")
        return list(chs.values())

    @classmethod
    def get(cls, ch_id):
        return next((c for c in cls.channels() if c["id"] == ch_id), None)

    # ------------------------------------------------------------ resolve
    @classmethod
    def _resolve_kbs(cls, code):
        import requests
        r = requests.get(f"https://cfpwwwapi.kbs.co.kr/api/v1/landing/live/channel_code/{code}",
                         headers=UA, timeout=10)
        r.raise_for_status()
        j = r.json()
        for item in j.get("channel_item") or []:
            if item.get("service_url"):
                return item["service_url"]
        raise Exception(f"KBS 응답에 service_url 없음: {str(j)[:200]}")

    @classmethod
    def _resolve_mbc(cls, code):
        import requests
        r = requests.get("https://sminiplay.imbc.com/aacplay.ashx",
                         params={"agent": "webapp", "channel": code}, headers=UA, timeout=10)
        r.raise_for_status()
        url = r.text.strip()
        if not url.startswith("http"):
            raise Exception(f"MBC 응답 이상: {url[:200]}")
        return url

    @classmethod
    def resolve(cls, ch_id, use_cache=True):
        ch = cls.get(ch_id)
        if ch is None:
            raise Exception(f"채널 없음: {ch_id}")
        if ch["type"] == "static":
            return ch["url"]
        hit = _cache.get(ch_id)
        if use_cache and hit and time.time() - hit[0] < CACHE_TTL:
            return hit[1]
        if ch["type"] == "kbs":
            url = cls._resolve_kbs(ch["code"])
        else:
            url = cls._resolve_mbc(ch["code"])
        _cache[ch_id] = (time.time(), url)
        return url

    @classmethod
    def warm(cls):
        """스케줄러용: 전체 채널 주소를 미리 받아 캐시."""
        ok = 0
        for c in cls.ch_list():
            try:
                cls.resolve(c["id"], use_cache=False)
                ok += 1
            except Exception as e:
                P.logger.warning(f'{c["name"]} 실패: {e}')
        P.logger.info(f"채널 주소 갱신 {ok}개")
        return ok

    # ------------------------------------------------------------ views
    @classmethod
    def ch_list(cls):
        flt = [x.strip() for x in (P.ModelSetting.get("region_filter") or "").split(",") if x.strip()]
        return [{"id": c["id"], "region": c["region"], "name": c["name"], "type": c["type"]}
                for c in cls.channels() if not flt or c["region"] in flt]

    @classmethod
    def make_m3u(cls):
        from tool import ToolUtil
        direct = P.ModelSetting.get("m3u_url_type") == "direct"
        lines = ["#EXTM3U"]
        for c in cls.ch_list():
            name = c["name"].replace('"', "'")
            if direct:
                try:
                    url = cls.resolve(c["id"])
                except Exception as e:
                    P.logger.warning(f'{c["name"]} 제외: {e}')
                    continue
            else:
                url = ToolUtil.make_apikey_url(f"/{P.package_name}/api/url?ch_id={c['id']}")
            lines.append(f'#EXTINF:-1 tvg-id="{c["id"]}" tvg-name="{name}" group-title="{c["region"]}",{c["name"]}')
            lines.append(url)
        return Response("\n".join(lines) + "\n", headers={"Content-Type": "audio/x-mpegurl; charset=utf-8"})

    @classmethod
    def url(cls, req):
        ch_id = req.args.get("ch_id")
        try:
            return redirect(cls.resolve(ch_id))
        except Exception as e:
            P.logger.error(f"url error ({ch_id}): {e}")
            return jsonify({"ret": "error", "msg": str(e)})
