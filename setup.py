setting = {
    "filepath": __file__,
    "use_db": True,
    "use_default_setting": True,
    "home_module": None,
    "menu": {
        "uri": __package__,
        "name": "라디오",
        "list": [
            {"uri": "main/setting", "name": "설정"},
            {"uri": "main/list", "name": "채널 목록"},
            {"uri": "log", "name": "로그"},
        ],
    },
    "setting_menu": None,
    "default_route": "normal",
}

from plugin import *

P = create_plugin_instance(setting)

try:
    from .mod_main import ModuleMain

    P.set_module_list([ModuleMain])
except Exception as e:
    P.logger.error(f"Exception:{str(e)}")
    P.logger.error(traceback.format_exc())
