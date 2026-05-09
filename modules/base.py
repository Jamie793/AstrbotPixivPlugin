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

    def cfg(self):
        return self.config_service.cfg()

    def _collect_illust_detail(self, *args, **kwargs):
        return self.illust._collect_illust_detail(*args, **kwargs)

    def _collect_my_bookmarks(self, *args, **kwargs):
        return self.illust._collect_my_bookmarks(*args, **kwargs)

    def _collect_my_following(self, *args, **kwargs):
        return self.illust._collect_my_following(*args, **kwargs)

    def _get_api_user_id(self, *args, **kwargs):
        return self.social._get_api_user_id(*args, **kwargs)

    def _looks_auth_failed(self, *args, **kwargs):
        return self.auth._looks_auth_failed(*args, **kwargs)

    def _plain_item(self, *args, **kwargs):
        return self.sender._plain_item(*args, **kwargs)

    def admin_denied_text(self, *args, **kwargs):
        return self.permissions.admin_denied_text(*args, **kwargs)

    def admin_mark(self, *args, **kwargs):
        return self.misc.admin_mark(*args, **kwargs)

    def allow_r18_for_event(self, *args, **kwargs):
        return self.permissions.allow_r18_for_event(*args, **kwargs)

    def and_match(self, *args, **kwargs):
        return self.query.and_match(*args, **kwargs)

    def api(self, *args, **kwargs):
        return self.auth.api(*args, **kwargs)

    def api_call(self, *args, **kwargs):
        return self.auth.api_call(*args, **kwargs)

    def api_no_auth_requests_call(self, *args, **kwargs):
        return self.auth.api_no_auth_requests_call(*args, **kwargs)

    def api_requests_call(self, *args, **kwargs):
        return self.auth.api_requests_call(*args, **kwargs)

    def auto_clean_loop(self, *args, **kwargs):
        return self.cache.auto_clean_loop(*args, **kwargs)

    def build_help_text(self, *args, **kwargs):
        return self.misc.build_help_text(*args, **kwargs)

    def build_novel_preview_infos(self, *args, **kwargs):
        return self.sender.build_novel_preview_infos(*args, **kwargs)

    def clean_download_cache(self, *args, **kwargs):
        return self.cache.clean_download_cache(*args, **kwargs)

    def collect_and_or(self, *args, **kwargs):
        return self.illust.collect_and_or(*args, **kwargs)

    def collect_discovery(self, *args, **kwargs):
        return self.illust.collect_discovery(*args, **kwargs)

    def collect_end_reason_text(self, *args, **kwargs):
        return self.query.collect_end_reason_text(*args, **kwargs)

    def collect_page_search(self, *args, **kwargs):
        return self.illust.collect_page_search(*args, **kwargs)

    def collect_paginated_illust(self, *args, **kwargs):
        return self.illust.collect_paginated_illust(*args, **kwargs)

    def collect_paginated_novel(self, *args, **kwargs):
        return self.novel.collect_paginated_novel(*args, **kwargs)

    def collect_paginated_users(self, *args, **kwargs):
        return self.social.collect_paginated_users(*args, **kwargs)

    def collect_rank(self, *args, **kwargs):
        return self.illust.collect_rank(*args, **kwargs)

    def collect_user(self, *args, **kwargs):
        return self.illust.collect_user(*args, **kwargs)

    def configured_cache_dir_text(self, *args, **kwargs):
        return self.cache.configured_cache_dir_text(*args, **kwargs)

    def contains_r18_query(self, *args, **kwargs):
        return self.permissions.contains_r18_query(*args, **kwargs)

    def convert_image_proxy_url(self, *args, **kwargs):
        return self.downloader.convert_image_proxy_url(*args, **kwargs)

    def create_api(self, *args, **kwargs):
        return self.auth.create_api(*args, **kwargs)

    def debug_resp_keys(self, *args, **kwargs):
        return self.query.debug_resp_keys(*args, **kwargs)

    def dispatch_illust_result(self, *args, **kwargs):
        return self.sender.dispatch_illust_result(*args, **kwargs)

    def dispatch_novel_result(self, *args, **kwargs):
        return self.sender.dispatch_novel_result(*args, **kwargs)

    def download_url(self, *args, **kwargs):
        return self.downloader.download_url(*args, **kwargs)

    def effective_search_max_depth(self, *args, **kwargs):
        return self.query.effective_search_max_depth(*args, **kwargs)

    def effective_start_page(self, *args, **kwargs):
        return self.query.effective_start_page(*args, **kwargs)

    def extract_first_illust(self, *args, **kwargs):
        return self.illust.extract_first_illust(*args, **kwargs)

    def extract_qq_arg(self, *args, **kwargs):
        return self.permissions.extract_qq_arg(*args, **kwargs)

    def extract_users(self, *args, **kwargs):
        return self.social.extract_users(*args, **kwargs)

    def fetch_novel_text(self, *args, **kwargs):
        return self.novel.fetch_novel_text(*args, **kwargs)

    def filter_reason(self, *args, **kwargs):
        return self.permissions.filter_reason(*args, **kwargs)

    def first_at_qq(self, *args, **kwargs):
        return self.permissions.first_at_qq(*args, **kwargs)

    def format_autocomplete(self, *args, **kwargs):
        return self.misc.format_autocomplete(*args, **kwargs)

    def format_cache_list(self, *args, **kwargs):
        return self.cache.format_cache_list(*args, **kwargs)

    def format_size(self, *args, **kwargs):
        return self.cache.format_size(*args, **kwargs)

    def format_trending_tags(self, *args, **kwargs):
        return self.social.format_trending_tags(*args, **kwargs)

    def format_users(self, *args, **kwargs):
        return self.social.format_users(*args, **kwargs)

    def generate_zip_password(self, *args, **kwargs):
        return self.downloader.generate_zip_password(*args, **kwargs)

    def is_bot_admin(self, *args, **kwargs):
        return self.permissions.is_bot_admin(*args, **kwargs)

    def is_group_event(self, *args, **kwargs):
        return self.permissions.is_group_event(*args, **kwargs)

    def is_owner(self, *args, **kwargs):
        return self.permissions.is_owner(*args, **kwargs)

    def is_r18_query_term(self, *args, **kwargs):
        return self.permissions.is_r18_query_term(*args, **kwargs)

    def load_last_items(self, *args, **kwargs):
        return self.cache.load_last_items(*args, **kwargs)

    def load_last_zip(self, *args, **kwargs):
        return self.cache.load_last_zip(*args, **kwargs)

    def load_r18_whitelist(self, *args, **kwargs):
        return self.permissions.load_r18_whitelist(*args, **kwargs)

    def load_token_state(self, *args, **kwargs):
        return self.auth.load_token_state(*args, **kwargs)

    def match_tag_filter(self, *args, **kwargs):
        return self.query.match_tag_filter(*args, **kwargs)

    def merge_tag_filters(self, *args, **kwargs):
        return self.query.merge_tag_filters(*args, **kwargs)

    def new_zip_writer(self, *args, **kwargs):
        return self.downloader.new_zip_writer(*args, **kwargs)

    def next_clean_time(self, *args, **kwargs):
        return self.cache.next_clean_time(*args, **kwargs)

    def parse_query_count(self, *args, **kwargs):
        return self.query.parse_query_count(*args, **kwargs)

    def parse_query_count_tags(self, *args, **kwargs):
        return self.query.parse_query_count_tags(*args, **kwargs)

    def pass_filter(self, *args, **kwargs):
        return self.permissions.pass_filter(*args, **kwargs)

    def path_total_size(self, *args, **kwargs):
        return self.cache.path_total_size(*args, **kwargs)

    def persist_rotated_refresh_token(self, *args, **kwargs):
        return self.auth.persist_rotated_refresh_token(*args, **kwargs)

    def pixiv_autocomplete(self, *args, **kwargs):
        return self.misc.pixiv_autocomplete(*args, **kwargs)

    def pop_zip_password(self, *args, **kwargs):
        return self.downloader.pop_zip_password(*args, **kwargs)

    def prepare_illust_files(self, *args, **kwargs):
        return self.downloader.prepare_illust_files(*args, **kwargs)

    def prepare_novel_files(self, *args, **kwargs):
        return self.downloader.prepare_novel_files(*args, **kwargs)

    def prepare_original_zip_from_items(self, *args, **kwargs):
        return self.downloader.prepare_original_zip_from_items(*args, **kwargs)

    def prepare_with_live_progress(self, *args, **kwargs):
        return self.downloader.prepare_with_live_progress(*args, **kwargs)

    def r18_query_denied_text(self, *args, **kwargs):
        return self.permissions.r18_query_denied_text(*args, **kwargs)

    def refresh_api_silent(self, *args, **kwargs):
        return self.auth.refresh_api_silent(*args, **kwargs)

    def refresh_token_keepalive_loop(self, *args, **kwargs):
        return self.auth.refresh_token_keepalive_loop(*args, **kwargs)

    def remember_zip_password(self, *args, **kwargs):
        return self.downloader.remember_zip_password(*args, **kwargs)

    def require_admin_feature(self, *args, **kwargs):
        return self.permissions.require_admin_feature(*args, **kwargs)

    def require_r18_query_allowed(self, *args, **kwargs):
        return self.permissions.require_r18_query_allowed(*args, **kwargs)

    def require_write_permission(self, *args, **kwargs):
        return self.permissions.require_write_permission(*args, **kwargs)

    def restore_token_state_to_api(self, *args, **kwargs):
        return self.auth.restore_token_state_to_api(*args, **kwargs)

    def run_illust_job(self, *args, **kwargs):
        return self.illust.run_illust_job(*args, **kwargs)

    def run_novel_job(self, *args, **kwargs):
        return self.novel.run_novel_job(*args, **kwargs)

    def save_last_items(self, *args, **kwargs):
        return self.cache.save_last_items(*args, **kwargs)

    def save_last_zip(self, *args, **kwargs):
        return self.cache.save_last_zip(*args, **kwargs)

    def save_r18_whitelist(self, *args, **kwargs):
        return self.permissions.save_r18_whitelist(*args, **kwargs)

    def save_token_state(self, *args, **kwargs):
        return self.auth.save_token_state(*args, **kwargs)

    def send_forward(self, *args, **kwargs):
        return self.sender.send_forward(*args, **kwargs)

    def send_images(self, *args, **kwargs):
        return self.sender.send_images(*args, **kwargs)

    def send_zip(self, *args, **kwargs):
        return self.sender.send_zip(*args, **kwargs)

    def sender_id(self, *args, **kwargs):
        return self.permissions.sender_id(*args, **kwargs)

    def set_collect_end_reason(self, *args, **kwargs):
        return self.query.set_collect_end_reason(*args, **kwargs)

    def set_debug_info(self, *args, **kwargs):
        return self.query.set_debug_info(*args, **kwargs)

    def split_include_exclude_tags(self, *args, **kwargs):
        return self.query.split_include_exclude_tags(*args, **kwargs)

    def user_facing_error(self, *args, **kwargs):
        return self.auth.user_facing_error(*args, **kwargs)

    def yield_pack_progress(self, *args, **kwargs):
        return self.downloader.yield_pack_progress(*args, **kwargs)
