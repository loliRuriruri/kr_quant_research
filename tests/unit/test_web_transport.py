from fastapi import FastAPI
from fastapi.testclient import TestClient
from kr_quant.web.transport import ResearchCompression


def test_research_compression_preserves_json_and_avoids_secrets():
    app = FastAPI()
    app.add_middleware(ResearchCompression)
    payload = {"rows": [{"ticker": "005930", "company": "삼성전자", "value": 42}] * 100}

    @app.get('/api/results/all')
    def research():
        return payload

    @app.get('/api/settings/raw')
    def settings():
        return payload

    with TestClient(app) as client:
        gz = client.get('/api/results/all', headers={'Accept-Encoding': 'gzip'})
        plain = client.get('/api/results/all', headers={'Accept-Encoding': 'identity'})
        assert gz.json() == plain.json() == payload
        assert gz.headers['content-encoding'] == 'gzip'
        assert 'accept-encoding' in gz.headers['vary'].lower()
        assert int(gz.headers['content-length']) < int(plain.headers['content-length']) / 5
        assert 'content-encoding' not in client.get('/api/settings/raw', headers={'Accept-Encoding': 'gzip'}).headers
