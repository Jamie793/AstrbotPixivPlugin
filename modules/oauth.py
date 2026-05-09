import base64
import hashlib
import json
import secrets
import time
import urllib.parse
from pathlib import Path

import aiohttp

AUTH_TOKEN_URL = 'https://oauth.secure.pixiv.net/auth/token'
LOGIN_URL = 'https://app-api.pixiv.net/web/v1/login'
REDIRECT_URI = 'https://app-api.pixiv.net/web/v1/users/auth/pixiv/callback'
# Pixiv 官方 Android App OAuth 公共客户端参数，用于 App API PKCE 登录流程。
# 这不是本插件作者的私有密钥；如 Pixiv 官方客户端参数变更，需要同步更新。
CLIENT_ID = 'MOBrBDS8blbauoSck0ZfDbtuzpyT'
CLIENT_SECRET = 'lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj'
USER_AGENT = 'PixivAndroidApp/5.0.234 (Android 11; Pixel 5)'


def s256(data: bytes) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode('ascii')


def generate_login_url(state_path: Path) -> str:
    code_verifier = secrets.token_urlsafe(32)
    code_challenge = s256(code_verifier.encode('ascii'))
    payload = {
        'code_verifier': code_verifier,
        'code_challenge': code_challenge,
        'created_at': int(time.time()),
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    params = {
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
        'client': 'pixiv-android',
    }
    return LOGIN_URL + '?' + urllib.parse.urlencode(params)


def extract_code(text: str) -> str:
    text = (text or '').strip()
    if not text:
        return ''
    parsed = urllib.parse.urlparse(text)
    qs = urllib.parse.parse_qs(parsed.query)
    if 'code' in qs and qs['code']:
        return qs['code'][0]
    if 'code=' in text:
        qs = urllib.parse.parse_qs(text.split('?', 1)[-1])
        if 'code' in qs and qs['code']:
            return qs['code'][0]
    if '&' not in text and '=' not in text and len(text) > 10:
        return text
    return ''


def parse_json_or_raw(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {'raw': raw}


async def exchange_token(callback_text: str, state_path: Path) -> dict:
    code = extract_code(callback_text)
    if not code:
        return {'error': 'code_not_found', 'hint': '请发送包含 code= 的 Pixiv 回调链接'}
    try:
        state = json.loads(state_path.read_text(encoding='utf-8'))
        try:
            state_path.unlink()
        except OSError:
            pass
    except (OSError, json.JSONDecodeError):
        return {'error': 'oauth_state_not_found', 'hint': '请先发送 /pixiv_get_token 生成登录链接'}
    code_verifier = state.get('code_verifier')
    if not code_verifier:
        return {'error': 'code_verifier_not_found', 'hint': '请重新发送 /pixiv_get_token'}
    form = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': code,
        'code_verifier': code_verifier,
        'grant_type': 'authorization_code',
        'include_policy': 'true',
        'redirect_uri': REDIRECT_URI,
    }
    headers = {
        'User-Agent': USER_AGENT,
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    timeout = aiohttp.ClientTimeout(total=30)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(AUTH_TOKEN_URL, data=form, headers=headers) as resp:
                raw = await resp.text(encoding='utf-8', errors='replace')
                return parse_json_or_raw(raw)
    except aiohttp.ClientError as e:
        return {'error': str(e)}
    except TimeoutError as e:
        return {'error': str(e)}


def token_parts(obj: dict):
    access_token = obj.get('access_token') or obj.get('response', {}).get('access_token')
    refresh_token = obj.get('refresh_token') or obj.get('response', {}).get('refresh_token')
    return access_token, refresh_token
