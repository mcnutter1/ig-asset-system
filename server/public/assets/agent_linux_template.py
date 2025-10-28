import os, sys, time, json, platform, socket, uuid, subprocess
from urllib.request import Request, urlopen

def get_ips():
    ips = set()
    try:
        hostname = socket.gethostname()
        for addr in socket.getaddrinfo(hostname, None):
            ip = addr[4][0]
            if ':' in ip or ip.count(':') >= 2:
                ips.add(ip)  # ipv6
            elif ip.count('.')==3:
                ips.add(ip)  # ipv4
    except Exception:
        pass
    return list(ips)

def get_mac():
    try:
        mac = uuid.getnode()
        return ':'.join(['%012x' % mac][0][i:i+2] for i in range(0,12,2))
    except Exception:
        return None

def collect():
    return {
        "name": platform.node(),
        "type": "workstation",
        "mac": get_mac(),
        "ips": get_ips(),
        "attributes": {
            "os": {
                "family": "linux",
                "dist": " ".join([platform.system(), platform.release()]),
                "version": platform.version(),
                "kernel": platform.release(),
            },
            "hardware": {
                "arch": platform.machine()
            },
            "apps": []
        }
    }

def post(url, token, payload):
    data = json.dumps(payload).encode('utf-8')
    req = Request(url, data=data, headers={
        "Content-Type":"application/json",
        "X-Agent-Token": token
    })
    with urlopen(req, timeout=20) as r:
        return r.read()

def main():
    token = globals().get("TOKEN")
    api = globals().get("API_URL")
    if not token or not api:
        print("Missing token or API_URL")
        sys.exit(2)
    while True:
        asset = collect()
        payload = {"asset": asset, "online_status": True}
        try:
            post(api, token, payload)
            # print("Heartbeat sent")
        except Exception as e:
            # print("Error:", e)
            pass
        time.sleep(60)

if __name__ == "__main__":
    main()
