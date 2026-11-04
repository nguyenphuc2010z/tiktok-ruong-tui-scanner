import json, time, urllib.request, urllib.parse, os

DEVICE_CODE = "77f52ac4dbbf4d452e110795a26967578d3251d3"
CLIENT_ID = "178c6fc778ccc68e1d6a"

def post(url, data):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                 headers={"Accept": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read().decode())

deadline = time.time() + 880
while time.time() < deadline:
    try:
        r = post("https://github.com/login/oauth/access_token", {
            "client_id": CLIENT_ID,
            "device_code": DEVICE_CODE,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        })
    except Exception as e:
        time.sleep(5); continue
    if "access_token" in r:
        open("/tmp/gh_token.txt", "w").write(r["access_token"])
        os.chmod("/tmp/gh_token.txt", 0o600)
        print("TOKEN_OK", flush=True)
        break
    err = r.get("error")
    if err == "authorization_pending":
        time.sleep(5)
    elif err == "slow_down":
        time.sleep(8)
    elif err in ("expired_token", "access_denied"):
        print("FAIL", err, flush=True); break
    else:
        time.sleep(5)
