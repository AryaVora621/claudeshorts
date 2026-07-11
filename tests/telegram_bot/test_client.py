from __future__ import annotations

import httpx

from claudeshorts.telegram_bot.client import ApiClient


def _mock_client(handler):
    return ApiClient(base_url="http://testserver", transport=httpx.MockTransport(handler))


def test_generate_posts_to_pipeline_generate():
    seen = {}
    def handler(request):
        seen["method"], seen["path"], seen["json"] = request.method, request.url.path, httpx.Request(request.method, request.url, content=request.content).content
        return httpx.Response(202, json={"job_id": 7})
    client = _mock_client(handler)
    result = client.generate(3)
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/v1/pipeline/generate"
    assert result == {"job_id": 7}


def test_list_posts_with_status_filter():
    def handler(request):
        assert request.url.path == "/api/v1/posts"
        assert dict(request.url.params) == {"status": "rendered"}
        return httpx.Response(200, json=[{"id": 1, "title": "T"}])
    client = _mock_client(handler)
    assert client.list_posts(status="rendered") == [{"id": 1, "title": "T"}]


def test_approve_calls_correct_endpoint():
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/api/v1/posts/5/approve"
        return httpx.Response(200, json={"post_id": 5, "exported": True, "scheduled_for": None})
    client = _mock_client(handler)
    result = client.approve(5)
    assert result["exported"] is True


def test_retry_job_calls_correct_endpoint():
    def handler(request):
        assert request.url.path == "/api/v1/jobs/9/retry"
        return httpx.Response(200, json={"job_id": 10})
    client = _mock_client(handler)
    assert client.retry_job(9) == {"job_id": 10}


def test_list_profiles():
    def handler(request):
        assert request.url.path == "/api/v1/profiles"
        return httpx.Response(200, json=[{"slug": "a", "platform": "youtube", "login_health": "ok"}])
    client = _mock_client(handler)
    assert client.list_profiles()[0]["slug"] == "a"
