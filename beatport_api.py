import base64
import hashlib
import secrets
from datetime import timedelta, datetime

from utils.utils import create_requests_session


class BeatportApi:
    def __init__(self):
        self.API_URL = "https://api.beatport.com/v4/"
        self.ACCOUNT_URL = "https://account.beatport.com/"

        # client id from the Beatport android app
        self.client_id = "5yfTsQ6B31nNXPsImGyeZiZ6oDzDiwG50E7FS92j"

        self.access_token = None
        self.refresh_token = None
        self.expires = None

        # required for the cookies
        self.s = create_requests_session()

    def headers(self, use_access_token: bool = False):
        return {
            'user-agent': 'okhttp/4.12.0',
            'authorization': f'Bearer {self.access_token}' if use_access_token else None,
        }

    def auth(self, username: str, password: str) -> dict:
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=')
        code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier).digest()).rstrip(b'=')
        redirect_uri = "beatport://bp_mobile_oauth"

        acc_headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 "
                          "Mobile Safari/537.36",
        }

        # authorize the code_challenge
        r = self.s.get(f"{self.ACCOUNT_URL}o/authorize/", params={
            "client_id": self.client_id,
            "response_type": "code",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "redirect_uri": redirect_uri,
        }, headers=acc_headers, allow_redirects=False)

        if r.status_code != 302:
            raise ConnectionError(r.text)

        r = self.s.post(f"{self.ACCOUNT_URL}identity/v1/login/", json={
            "username": username,
            "password": password,
        }, headers=acc_headers)

        if r.status_code != 200:
            raise ConnectionError(r.text)

        # get the code from the redirect url, that's why redirect is disabled
        r = self.s.get('https://account.beatport.com/o/authorize/', params={
            "client_id": self.client_id,
            "response_type": "code",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "redirect_uri": redirect_uri,
        }, headers=acc_headers, allow_redirects=False)

        if r.status_code != 302:
            raise ConnectionError(r.text)

        # get the code from the redirect url
        code = r.headers['location'].split('code=')[1]

        # exchange the code for the access_token, refresh_token and expires_in
        r = self.s.post(f'https://account.beatport.com/o/token/', data={
            "client_id": self.client_id,
            "code_verifier": code_verifier,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        })

        if r.status_code != 200:
            raise ConnectionError(r.text)

        # convert to JSON
        r = r.json()

        # save all tokens with access_token expiry date
        self.access_token = r['access_token']
        self.refresh_token = r['refresh_token']
        self.expires = datetime.now() + timedelta(seconds=r['expires_in'])

        return r

    def refresh(self):
        r = self.s.post(f'{self.API_URL}auth/o/token/', data={
            'client_id': self.client_id,
            'refresh_token': self.refresh_token,
            'grant_type': 'refresh_token',
        })

        if r.status_code != 200:
            return r.json()

        self.access_token = r.json()['access_token']
        self.refresh_token = r.json()['refresh_token']
        self.expires = datetime.now() + timedelta(seconds=r.json()['expires_in'])

    def set_session(self, session: dict):
        self.access_token = session.get('access_token')
        self.refresh_token = session.get('refresh_token')
        self.expires = session.get('expires')

    def get_session(self):
        return {
            'access_token': self.access_token,
            'refresh_token': self.refresh_token,
            'expires': self.expires
        }

    def _get(self, endpoint: str, params: dict = None):
        # function for API requests
        if not params:
            params = {}

        r = self.s.get(f'{self.API_URL}{endpoint}', params=params, headers=self.headers(use_access_token=True))

        # access_token expired
        if r.status_code == 401:
            raise ValueError(r.text)

        if r.status_code not in {200, 201, 202}:
            raise ConnectionError(r.text)

        return r.json()

    def get_account(self):
        return self._get('auth/o/introspect')

    def get_track(self, track_id: str):
        return self._get(f'catalog/tracks/{track_id}')

    def get_release(self, release_id: str):
        return self._get(f'catalog/releases/{release_id}')

    def get_release_tracks(self, release_id: str, page: int = 1, per_page: int = 100):
        return self._get(f'catalog/releases/{release_id}/tracks', params={
            'page': page,
            'per_page': per_page
        })

    def get_playlist(self, playlist_id: str):
        return self._get(f'catalog/playlists/{playlist_id}')

    def get_playlist_tracks(self, playlist_id: str, page: int = 1, per_page: int = 100):
        return self._get(f'catalog/playlists/{playlist_id}/tracks', params={
            'page': page,
            'per_page': per_page
        })

    def get_chart(self, chart_id: str):
        return self._get(f'catalog/charts/{chart_id}')

    def get_chart_tracks(self, chart_id: str, page: int = 1, per_page: int = 100):
        return self._get(f'catalog/charts/{chart_id}/tracks', params={
            'page': page,
            'per_page': per_page
        })

    def get_artist(self, artist_id: str):
        return self._get(f'catalog/artists/{artist_id}')

    def get_artist_tracks(self, artist_id: str, page: int = 1, per_page: int = 100):
        return self._get(f'catalog/artists/{artist_id}/tracks', params={
            'page': page,
            'per_page': per_page
        })

    def get_label(self, label_id: str):
        return self._get(f'catalog/labels/{label_id}')

    def get_label_releases(self, label_id: str):
        return self._get(f'catalog/labels/{label_id}/releases')

    def get_search(self, query: str):
        return self._get('catalog/search', params={'q': query})

    def get_track_stream(self, track_id: str):
        # get the 128k stream (.m3u8) for a given track id from needledrop.beatport.com
        return self._get(f'catalog/tracks/{track_id}/stream')

    def get_track_download(self, track_id: str, quality: str):
        # get the 256k stream (.mp4) for a given track id
        return self._get(f'catalog/tracks/{track_id}/download', params={'quality': quality})
