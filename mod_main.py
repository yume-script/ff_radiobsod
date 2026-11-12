from datetime import datetime

from tool import ToolUtil
from flask import Response

from .setup import *

import os

try:
    if os.path.exists(os.path.join(os.path.dirname(__file__), "source_radio_handler.py")):
        from .source_radio_handler import RadioHandler
    else:
        raise ImportError("source_radio_handler.py not found")
except Exception as e:
    P.logger.error(f"handler import error: {str(e)}")
    P.logger.error(traceback.format_exc())
    RadioHandler = None


class ModuleMain(PluginModuleBase):
    def __init__(self, P):
        super(ModuleMain, self).__init__(P, name="main", first_menu="setting", scheduler_desc="라디오 채널 주소 갱신")
        self.db_default = {
            f"{self.name}_db_version": "2",
            f"{self.name}_auto_start": "False",
            f"{self.name}_interval": "10",
            "m3u_url_type": "redirect",  # redirect: 재생 시점에 새 주소로 연결(권장) / direct: M3U 생성 시점 주소
            "region_filter": "",  # 비우면 전체, 예: 수도권
        }

    def process_menu(self, sub, req):
        arg = P.ModelSetting.to_dict()
        arg["api_m3u"] = ToolUtil.make_apikey_url(f"/{P.package_name}/api/m3u")
        arg["api_json"] = ToolUtil.make_apikey_url(f"/{P.package_name}/api/json")
        if sub == "setting":
            arg["is_include"] = F.scheduler.is_include(self.get_scheduler_name())
            arg["is_running"] = F.scheduler.is_running(self.get_scheduler_name())
            arg["custom_path"] = RadioHandler.custom_path() if RadioHandler else ""
        return render_template(f"{P.package_name}_{self.name}_{sub}.html", arg=arg)

    def process_command(self, command, arg1, arg2, arg3, req):
        updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if RadioHandler is None:
            return jsonify({"ret": "danger", "msg": "핸들러 로드 실패(로그 확인)", "list": [], "data": None,
                            "updated_at": "에러: 핸들러 로드 실패"})
        try:
            if command == "broad_list":
                return jsonify({"list": RadioHandler.ch_list(), "updated_at": updated_at})
            elif command == "play_url":
                direct = RadioHandler.resolve(arg1)
                url = ToolUtil.make_apikey_url(f"/{P.package_name}/api/url?ch_id={arg1}")
                return jsonify({"ret": "success", "data": url, "direct": direct})
            elif command == "refresh":
                n = RadioHandler.warm()
                return jsonify({"ret": "success", "msg": f"{n}개 채널 주소 갱신 완료"})
        except Exception as e:
            P.logger.error(f"command {command} error: {str(e)}")
            P.logger.error(traceback.format_exc())
            return jsonify({"ret": "danger", "msg": str(e), "data": None, "list": [], "updated_at": f"에러: {str(e)}"})

    def process_api(self, sub, req):
        try:
            if sub == "m3u":
                return RadioHandler.make_m3u()
            elif sub == "json":
                return jsonify(RadioHandler.ch_list())
            elif sub == "url":
                return RadioHandler.url(req)
        except Exception as e:
            P.logger.error(f"Exception:{str(e)}")
            P.logger.error(traceback.format_exc())

    def scheduler_function(self):
        try:
            RadioHandler.warm()
        except Exception as e:
            P.logger.error(f"Exception:{str(e)}")
            P.logger.error(traceback.format_exc())
