class BaseService:
    def __init__(self, plugin):
        self.p = plugin

    @property
    def config(self):
        return self.p.config

    @property
    def _api(self):
        return self.p._api

    @_api.setter
    def _api(self, value):
        self.p._api = value

    @property
    def _auth_lock(self):
        return self.p._auth_lock

    @property
    def _task_lock(self):
        return self.p._task_lock

    @property
    def _current_allow_r18(self):
        return self.p._current_allow_r18

    @_current_allow_r18.setter
    def _current_allow_r18(self, value):
        self.p._current_allow_r18 = value

    @property
    def _current_start_page_override(self):
        return self.p._current_start_page_override

    @_current_start_page_override.setter
    def _current_start_page_override(self, value):
        self.p._current_start_page_override = value

    @property
    def _current_search_max_depth_override(self):
        return getattr(self.p, "_current_search_max_depth_override", None)

    @_current_search_max_depth_override.setter
    def _current_search_max_depth_override(self, value):
        self.p._current_search_max_depth_override = value

    @property
    def _last_count_limit_notice(self):
        return getattr(self.p, "_last_count_limit_notice", "")

    @_last_count_limit_notice.setter
    def _last_count_limit_notice(self, value):
        self.p._last_count_limit_notice = value

    @property
    def _last_collect_end_reason(self):
        return getattr(self.p, "_last_collect_end_reason", "未知原因")

    @_last_collect_end_reason.setter
    def _last_collect_end_reason(self, value):
        self.p._last_collect_end_reason = value

    @property
    def _last_debug(self):
        return self.p._last_debug

    @_last_debug.setter
    def _last_debug(self, value):
        self.p._last_debug = value

    @property
    def state(self):
        return self.p.state

    @property
    def config_service(self):
        return self.p.config_service

    @property
    def auth(self):
        return self.p.auth

    @property
    def cache(self):
        return self.p.cache

    @property
    def query(self):
        return self.p.query

    @property
    def permissions(self):
        return self.p.permissions

    @property
    def downloader(self):
        return self.p.downloader

    @property
    def sender(self):
        return self.p.sender

    @property
    def illust(self):
        return self.p.illust

    @property
    def novel(self):
        return self.p.novel

    @property
    def social(self):
        return self.p.social

    @property
    def misc(self):
        return self.p.misc

    @property
    def debug(self):
        return self.p.debug
