def test_hello_returns_200(client):
    response = client.get('/hello')
    assert response.status_code == 200

def test_rate_limit_trigger_429(client):
    for i in range(3):
        res = client.get("/hello")
        assert res.status_code == 200

    res = client.get("/hello")
    assert res.status_code == 429
