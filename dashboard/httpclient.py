"""Cliente HTTP compartilhado para a API do Kubernetes e o Thanos Querier.

Autentica com o token da ServiceAccount do pod e confia na CA do cluster e na
service-ca do OpenShift (usada pelo Thanos).
"""
import os
import tempfile

import requests

SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
TIMEOUT = 25


class ApiError(Exception):
    pass


def _ca_bundle():
    """Junta as CAs do sistema com as do cluster num arquivo temporário."""
    files = [f for f in (f"{SA_DIR}/ca.crt", f"{SA_DIR}/service-ca.crt") if os.path.exists(f)]
    if not files:
        return True  # só as CAs do sistema
    try:
        import certifi
        parts = [open(certifi.where()).read()]
    except Exception:
        parts = []
    for f in files:
        with open(f) as fh:
            parts.append(fh.read())
    bundle = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False, dir=tempfile.gettempdir())
    bundle.write("\n".join(parts))
    bundle.close()
    return bundle.name


class HttpClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.verify = _ca_bundle()

    def _token(self):
        # Lido a cada chamada: o OpenShift renova o token projetado periodicamente.
        try:
            with open(f"{SA_DIR}/token") as fh:
                return fh.read().strip()
        except OSError:
            return None

    def send_json(self, method, url, body, content_type="application/json"):
        """POST/PATCH/PUT com corpo JSON. Devolve (status, json ou None)."""
        headers = {"Content-Type": content_type}
        token = self._token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            resp = self.session.request(method, url, json=body, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise ApiError(str(exc)) from exc
        try:
            data = resp.json()
        except ValueError:
            data = None
        return resp.status_code, data

    def get_json(self, url, params=None):
        headers = {}
        token = self._token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise ApiError(str(exc)) from exc
        if resp.status_code != 200:
            raise ApiError(f"HTTP {resp.status_code}: {resp.text.strip()[:300]}")
        return resp.json()
