import asyncio
from astrbot.api import logger
from pixivpy3 import AppPixivAPI, ByPassSniApi
from .base import BaseService
from .errors import PIXIV_REFRESH_TOKEN_REQUIRED_MESSAGE, PixivRefreshTokenInvalidError

class AuthService(BaseService):
    def save_token_state(self, api=None):
        """保存运行期 Pixiv token 状态。/pixivc_get_token 获取流程不会调用这里。"""
        api = api or self._api
        access_token = str(getattr(api, "access_token", "") or "").strip()
        if not access_token:
            return
        payload = {
            "access_token": access_token,
        }
        self.state.set_section("token_state", payload)
        logger.info("Pixivc token 状态已静默保存到 state.json。")

    def load_token_state(self) -> dict:
        try:
            data = self.state.get_section("token_state", {})
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"Pixivc 读取本地 token 状态失败：{type(e).__name__}: {e}")
            return {}

    def restore_token_state_to_api(self, api) -> bool:
        """启动后把文件中的 access_token 恢复进 pixivpy3 实例；refresh_token 只读取插件配置。"""
        state = self.load_token_state()
        access_token = str(state.get("access_token") or "").strip()
        if not access_token:
            return False
        api.access_token = access_token
        config_refresh_token = str(self.config.get("refresh_token") or "").strip()
        if config_refresh_token:
            api.refresh_token = config_refresh_token
        logger.info("Pixivc 已从本地文件恢复 access token 状态。")
        return True

    def persist_rotated_refresh_token(self, api=None):
        """认证成功后，如果 pixivpy3 返回了新的 refresh_token，则静默写回本插件配置。"""
        api = api or self._api
        new_refresh_token = str(getattr(api, "refresh_token", "") or "").strip()
        old_refresh_token = str(self.config.get("refresh_token") or "").strip()
        if not new_refresh_token or new_refresh_token == old_refresh_token:
            return
        self.config["refresh_token"] = new_refresh_token
        try:
            if hasattr(self.config, "save_config"):
                self.config.save_config()
                logger.info("Pixivc 检测到新的 Refresh Token，已静默写回插件配置。")
            else:
                logger.info("Pixivc 检测到新的 Refresh Token，已更新运行时配置；当前配置对象不支持自动持久化。")
        except Exception as e:
            logger.error(f"Pixivc 写回新的 Refresh Token 失败：{type(e).__name__}: {e}")

    def get_refresh_token(self) -> str:
        return str(self.config.get("refresh_token") or "").strip()

    async def refresh_token_keepalive_loop(self):
        """插件开启状态下定时静默认证，避免 refresh_token 长期未使用。"""
        startup_delay = 60
        while True:
            try:
                await asyncio.sleep(startup_delay)
                c = self.config_service.cfg()
                interval_seconds = max(3600, int(c["refresh_token_interval_hours"] * 3600))
                startup_delay = interval_seconds
                refresh_token = self.get_refresh_token()
                if not refresh_token:
                    logger.warning("Pixivc Refresh Token 静默刷新跳过：未配置 refresh_token。")
                    continue
                logger.info("Pixivc Refresh Token 静默刷新开始。")
                await self.refresh_api_silent(reason="refresh_token_keepalive")
                logger.info("Pixivc Refresh Token 静默刷新成功。")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Pixivc Refresh Token 静默刷新失败：{type(e).__name__}: {e}", exc_info=True)
                await asyncio.sleep(300)

    def create_api(self, proxy: str):
        if proxy:
            return AppPixivAPI(proxies={"http": proxy, "https": proxy})
        try:
            return ByPassSniApi()
        except Exception:
            return AppPixivAPI()

    async def api(self):
        c = self.config_service.cfg()
        refresh_token = self.get_refresh_token()
        if not refresh_token:
            raise RuntimeError("未配置 Pixiv refresh_token，请在本插件设置中填写。")
        async with self._auth_lock:
            if self._api is None:
                self._api = self.create_api(c["proxy"])
                if not self.restore_token_state_to_api(self._api):
                    try:
                        await asyncio.to_thread(self._api.auth, refresh_token=refresh_token)
                    except Exception as e:
                        logger.warning(f"Pixivc 初次认证失败：{type(e).__name__}: {e}")
                        raise PixivRefreshTokenInvalidError(PIXIV_REFRESH_TOKEN_REQUIRED_MESSAGE) from e
                    self.persist_rotated_refresh_token(self._api)
                    self.save_token_state(self._api)
            return self._api

    def _looks_auth_failed(self, exc=None, resp=None) -> bool:
        if resp is not None:
            status = getattr(resp, "status_code", None)
            if status in (401, 403):
                return True
            # pixivpy3 的高级接口经常不会保留 HTTP status_code，
            # 而是直接返回 JsonDict: {"error": {...}}。
            # 这种情况下也应触发一次静默刷新，否则会被上层误判为“没有作品”。
            if isinstance(resp, dict) and resp.get("error"):
                return True
            try:
                err = resp.json()
            except Exception:
                err = None
            text = str(err if err is not None else getattr(resp, "text", ""))
        else:
            text = str(exc or "")
        lower = text.lower()
        return any(k in lower for k in ["invalid_grant", "invalid_request", "invalid token", "access token", "unauthorized", "oauth", "token expired", "expired token", "authentication required", "auth required", "call login", "set_auth", "login()"])

    def user_facing_error(self, e: Exception) -> str:
        if isinstance(e, PixivRefreshTokenInvalidError):
            return str(e)
        return str(e)

    async def refresh_api_silent(self, reason: str = "access_token_expired"):
        c = self.config_service.cfg()
        refresh_token = self.get_refresh_token()
        if not refresh_token:
            raise PixivRefreshTokenInvalidError(PIXIV_REFRESH_TOKEN_REQUIRED_MESSAGE)
        async with self._auth_lock:
            logger.info(f"Pixivc 正在后台静默刷新认证，reason={reason}。")
            self._api = self.create_api(c["proxy"])
            try:
                await asyncio.to_thread(self._api.auth, refresh_token=refresh_token)
            except Exception as e:
                logger.warning(f"Pixivc 使用 Refresh Token 刷新认证失败：{type(e).__name__}: {e}")
                raise PixivRefreshTokenInvalidError(PIXIV_REFRESH_TOKEN_REQUIRED_MESSAGE) from e
            self.persist_rotated_refresh_token(self._api)
            self.save_token_state(self._api)
            return self._api

    async def api_call(self, method_name: str, *args, **kwargs):
        api = await self.api()
        method = getattr(api, method_name)
        retried = False
        try:
            resp = await asyncio.to_thread(method, *args, **kwargs)
            if self._looks_auth_failed(resp=resp):
                retried = True
                api = await self.refresh_api_silent()
                resp = await asyncio.to_thread(getattr(api, method_name), *args, **kwargs)
            self.debug.record_api(method_name, args=args, kwargs=kwargs, resp=resp, retried=retried)
            return resp
        except Exception as e:
            if self._looks_auth_failed(exc=e):
                retried = True
                try:
                    api = await self.refresh_api_silent()
                    resp = await asyncio.to_thread(getattr(api, method_name), *args, **kwargs)
                    self.debug.record_api(method_name, args=args, kwargs=kwargs, resp=resp, retried=retried)
                    return resp
                except Exception as e2:
                    self.debug.record_api(method_name, args=args, kwargs=kwargs, error=e2, retried=retried)
                    raise
            self.debug.record_api(method_name, args=args, kwargs=kwargs, error=e, retried=retried)
            raise

    async def api_requests_call(self, method: str, url: str, **kwargs):
        api = await self.api()
        retried = False
        try:
            resp = await asyncio.to_thread(api.requests_call, method, url, **kwargs)
            if self._looks_auth_failed(resp=resp):
                retried = True
                api = await self.refresh_api_silent()
                resp = await asyncio.to_thread(api.requests_call, method, url, **kwargs)
            self.debug.record_api(f"requests_call:{method}", kwargs=kwargs, resp=resp, retried=retried, raw_url=url)
            return resp
        except Exception as e:
            if self._looks_auth_failed(exc=e):
                retried = True
                try:
                    api = await self.refresh_api_silent()
                    resp = await asyncio.to_thread(api.requests_call, method, url, **kwargs)
                    self.debug.record_api(f"requests_call:{method}", kwargs=kwargs, resp=resp, retried=retried, raw_url=url)
                    return resp
                except Exception as e2:
                    self.debug.record_api(f"requests_call:{method}", kwargs=kwargs, error=e2, retried=retried, raw_url=url)
                    raise
            self.debug.record_api(f"requests_call:{method}", kwargs=kwargs, error=e, retried=retried, raw_url=url)
            raise

    async def api_no_auth_requests_call(self, method: str, url: str, **kwargs):
        api = await self.api()
        retried = False
        try:
            resp = await asyncio.to_thread(api.no_auth_requests_call, method, url, req_auth=True, **kwargs)
            if self._looks_auth_failed(resp=resp):
                retried = True
                api = await self.refresh_api_silent()
                resp = await asyncio.to_thread(api.no_auth_requests_call, method, url, req_auth=True, **kwargs)
            self.debug.record_api(f"no_auth_requests_call:{method}", kwargs=kwargs, resp=resp, retried=retried, raw_url=url)
            return resp
        except Exception as e:
            if self._looks_auth_failed(exc=e):
                retried = True
                try:
                    api = await self.refresh_api_silent()
                    resp = await asyncio.to_thread(api.no_auth_requests_call, method, url, req_auth=True, **kwargs)
                    self.debug.record_api(f"no_auth_requests_call:{method}", kwargs=kwargs, resp=resp, retried=retried, raw_url=url)
                    return resp
                except Exception as e2:
                    self.debug.record_api(f"no_auth_requests_call:{method}", kwargs=kwargs, error=e2, retried=retried, raw_url=url)
                    raise
            self.debug.record_api(f"no_auth_requests_call:{method}", kwargs=kwargs, error=e, retried=retried, raw_url=url)
            raise
