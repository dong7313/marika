from review_benchmark.api import Client, code, json_object


def test_model_name_and_credentials(monkeypatch):
    monkeypatch.setenv('MODEL_API_KEY', 'test-only-not-a-real-credential')
    seen = {}
    class Response:
        ok = True
        def json(self):
            return {'choices': [{'message': {'content': '```python\nresult = 1\n```'}}]}
    def post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return Response()
    monkeypatch.setattr('review_benchmark.api.requests.post', post)
    text = Client('https://example.invalid/v1').complete('reviewer-selected-model', [])
    assert seen['json'] == {'model': 'reviewer-selected-model', 'messages': []}
    assert seen['headers']['Authorization'].startswith('Bearer ')
    assert 'test-only-not-a-real-credential' not in str(seen['json'])
    assert code(text) == 'result = 1\n'
    assert json_object('```json\n{"items": []}\n```') == {'items': []}
