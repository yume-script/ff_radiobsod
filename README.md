# ff_radiobsod

국내 라디오 채널의 스트림 주소를 방송사 서버에서 직접 받아 M3U / JSON 으로 제공하는 FlaskFarm 플러그인.
(radio.bsod.kr 은 Cloudflare 차단 때문에 서버에서 접속하지 않음)

- `/{package}/api/m3u?apikey=...` : 플레이어용 M3U (group-title = 지역)
- `/{package}/api/json?apikey=...` : 채널 목록 JSON
- `/{package}/api/url?ch_id=...`  : 재생 시점에 방송사에서 새 서명 주소를 받아 redirect

서명 주소는 만료되므로 저장하지 않고 재생 요청 때마다 받는다(5분 캐시).

## 기본 채널 (수도권)
KBS 1라디오·2라디오·3라디오·1FM·2FM·한민족방송, MBC 표준FM·FM4U·mini 올댓뮤직, EBS FM

## 자동 탐색
설정 화면의 'KBS 채널 자동 탐색' 버튼이 KBS 채널코드(1~150)를 훑어 라디오 채널을 `ff_radiobsod_discovered_channels.json` 에 저장한다. (지역 분류는 이름의 지역 키워드 기반, 못 찾으면 '기타')

## 채널 추가
`data/db/ff_radiobsod_custom_channels.json` 에 JSON 배열로 작성 (같은 id 면 기본값을 덮어씀).

```json
[
  {"id": "kbs_busan_1", "region": "부산·울산·경남", "name": "KBS부산 1라디오", "type": "kbs", "code": "채널코드"},
  {"id": "mbc_x", "region": "수도권", "name": "예시", "type": "mbc", "code": "mfm"},
  {"id": "ebs_x", "region": "수도권", "name": "고정주소 예시", "type": "static", "url": "https://.../playlist.m3u8"}
]
```
- `kbs`: `https://cfpwwwapi.kbs.co.kr/api/v1/landing/live/channel_code/{code}` 응답의 `service_url`
- `mbc`: `https://sminiplay.imbc.com/aacplay.ashx?agent=webapp&channel={code}` 응답 텍스트
- `static`: 고정 주소
