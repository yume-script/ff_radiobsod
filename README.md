# ff_radiobsod

radio.bsod.kr 지역별 라디오 채널 스트림 URL을 수집해 M3U / JSON 으로 제공하는 FlaskFarm 플러그인.

- `/{package}/api/m3u?apikey=...` : 플레이어(VLC, Kodi 등)용 M3U (group-title = 지역)
- `/{package}/api/json?apikey=...` : 전체 채널 JSON
- `/{package}/api/url?ch_id=...`  : 채널 스트림으로 redirect

설치: 플러그인 폴더(`ff_radiobsod`)를 FlaskFarm `plugins/` 아래에 넣고 재시작.
