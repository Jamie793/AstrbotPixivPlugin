import base64
import hashlib
import json
import secrets
import time
import urllib.parse
import urllib.request
from pathlib import Path

AUTH_TOKEN_URL = 'https://oauth.secure.pixiv.net/auth/token'
LOGIN_URL = 'https://app-api.pixiv.net/web/v1/login'
REDIRECT_URI = 'https://app-api.pixiv.net/web/v1/users/auth/pixiv/callback'
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


def exchange_token(callback_text: str, state_path: Path) -> dict:
    code = extract_code(callback_text)
    if not code:
        return {'error': 'code_not_found', 'hint': '请发送包含 code= 的 Pixiv 回调链接'}
    try:
        state = json.loads(state_path.read_text(encoding='utf-8'))
        try:
            state_path.unlink()
        except Exception:
            pass
    except Exception:
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
    data = urllib.parse.urlencode(form).encode('utf-8')
    req = urllib.request.Request(
        AUTH_TOKEN_URL,
        data=data,
        headers={
            'User-Agent': USER_AGENT,
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode('utf-8', 'replace')
            try:
                return json.loads(raw)
            except Exception:
                return {'raw': raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return json.loads(raw)
        except Exception:
            return {'raw': raw}
    except Exception as e:
        return {'error': str(e)}


def token_parts(obj: dict):
    access_token = obj.get('access_token') or obj.get('response', {}).get('access_token')
    refresh_token = obj.get('refresh_token') or obj.get('response', {}).get('refresh_token')
    return access_token, refresh_token
