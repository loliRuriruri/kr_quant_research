"""Compress read-only research responses, never settings/secrets or mutations."""
from starlette.middleware.gzip import GZipMiddleware


class ResearchCompression:
    def __init__(self, app):
        self.app = app
        self.compressed = GZipMiddleware(app, minimum_size=1500, compresslevel=5)

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        allowed = path.startswith(('/api/results/', '/api/seasonality/', '/api/flow', '/static/'))
        target = self.compressed if scope['type'] == 'http' and scope.get('method') == 'GET' and allowed else self.app
        await target(scope, receive, send)
