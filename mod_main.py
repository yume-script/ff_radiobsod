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
        super(ModuleMain, self).__init__(P, name="main", first_menu="setting", scheduler_desc="라디오 채널 동기화")
        self.db_default = {
            f"{self.name}_db_version": "1",
            f"{self.name}_auto_start": "False",
            f"{self.name}_interval": "1440",
            "source_url": "https://radio.bsod.kr/",
            "m3u_url_type": "redirect",  # redirect: 플러그인 경유 / direct: 원본 스트림 URL
            "region_filter": "",  # 비우면 전체, 예: 광주·전남,수도권
        }

    def process_menu(self, sub, req):
        arg = P.ModelSetting.to_dict()
        arg["api_m3u"] = ToolUtil.make_apikey_url(f"/{P.package_name}/api/m3u")
        arg["api_json"] = ToolUtil.make_apikey_url(f"/{P.package_name}/api/json")
        if sub == "setting":
            arg["is_include"] = F.scheduler.is_include(self.get_scheduler_name())
            arg["is_running"] = F.scheduler.is_running(self.get_scheduler_name())
        return render_template(f"{P.package_name}_{self.name}_{sub}.html", arg=arg)

    def process_command(self, command, arg1, arg2, arg3, req):
        updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if command == "broad_list":
            return jsonify({"list": RadioHandler.ch_list(), "updated_at": updated_at})
        elif command == "sync":
            n = RadioHandler.sync()
            return jsonify({"ret": "success", "msg": f"{n}개 채널 동기화 완료"})
        elif command == "play_url":
            url = ToolUtil.make_apikey_url(f"/{P.package_name}/api/url?ch_id={arg1}")
            return jsonify({"ret": "success", "data": url})

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
            RadioHandler.sync()
        except Exception as e:
            P.logger.error(f"Exception:{str(e)}")
            P.logger.error(traceback.format_exc())
