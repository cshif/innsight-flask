def test_tracing_headers_exist(client):
    res = client.get("/hello")
    assert 'X-Trace-ID' in res.headers

def test_tracing_headers_format(client):
    res = client.get("/hello")
    assert res.headers['X-Trace-ID'].startswith('req_')
    assert len(res.headers['X-Trace-ID']) == 12

def test_tracing_headers_uniqueness(client):
    res_1 = client.get("/hello")
    trace_id_1 = res_1.headers['X-Trace-ID']
    res_2 = client.get("/hello")
    trace_id_2 = res_2.headers['X-Trace-ID']
    assert trace_id_1 != trace_id_2
