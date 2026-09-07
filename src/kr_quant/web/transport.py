"""Lossless presentation transport for repeated flow category rows."""
import json
from starlette.middleware.gzip import GZipMiddleware


class ResearchCompression:
    def __init__(self, app):
        self.app = app
        self.compressed = GZipMiddleware(app, minimum_size=1500, compresslevel=5)

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        allowed = path.startswith(('/api/results/', '/api/seasonality/', '/api/flow', '/static/')) or path in {
            '/api/strategy', '/api/sectors', '/api/screens', '/api/market', '/api/macro', '/api/us13f'}
        target = self.compressed if scope['type'] == 'http' and scope.get('method') == 'GET' and allowed else self.app
        await target(scope, receive, send)


def pack_rows(payload):
    pool, lookup, groups = [], {}, {}
    result = dict(payload)
    for key, value in payload.items():
        if not isinstance(value, list) or not value or not all(
            isinstance(row, dict) and 'ticker' in row for row in value
        ):
            continue
        refs = []
        for row in value:
            # Different versions of the same ticker must not be merged.
            signature = json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)
            if signature not in lookup:
                lookup[signature] = len(pool)
                pool.append(row)
            refs.append(lookup[signature])
        groups[key] = refs
        del result[key]
    return {**result, '_row_transport': {'version': 1, 'pool': pool, 'groups': groups}}
