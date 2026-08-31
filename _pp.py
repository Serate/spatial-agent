import os, json, urllib.request, time
key = os.environ.get('OPENAI_API_KEY')
base = os.environ.get('OPENAI_BASE_URL')
model = os.environ.get('OPENAI_MODEL')
wire = os.environ.get('OPENAI_WIRE_API')
mode = os.environ.get('OPENAI_STRUCTURED_OUTPUT_MODE', 'json_object')
url = base.rstrip('/') + '/chat/completions'
body = {'model': model, 'messages': [{'role': 'user', 'content': 'Return JSON: {"ok": true}'}], 'max_tokens': 64}
if mode == 'json_object':
    body['response_format'] = {'type': 'json_object'}
t0 = time.time()
req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
    'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key}, method='POST')
try:
    resp = urllib.request.urlopen(req, timeout=120)
    data = resp.read().decode()
    print('HTTP', resp.status, 'elapsed=', round(time.time() - t0, 1), 's')
    print('RAW[:300]:', data[:300])
except Exception as e:
    print('ERR', repr(e), 'elapsed=', round(time.time() - t0, 1), 's')
