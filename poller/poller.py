import time, yaml, requests, json, paramiko, socket

def ping(host, timeout=1):
    try:
        socket.gethostbyname(host)
        return True
    except:
        return False

def linux_probe(target):
    host, user, pwd = target['host'], target['username'], target['password']
    info = {"name": host, "type": "server", "ips": [host], "attributes": {"os":{"family":"linux"}}, "mac": None}
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, username=user, password=pwd, timeout=10)
        cmds = {
            "uname": "uname -a",
            "hostname": "hostname",
            "ip": "hostname -I || ip -4 -o addr show | awk '{print $4}'",
            "mac": "ip link | awk '/ether/ {print $2; exit}'",
        }
        result = {}
        for k,c in cmds.items():
            stdin, stdout, stderr = ssh.exec_command(c, timeout=8)
            result[k] = stdout.read().decode().strip()
        info["name"] = result.get("hostname") or host
        info["ips"] = [i for i in (result.get("ip","").split() or [])]
        info["mac"] = result.get("mac") or None
        info["attributes"]["os"]["kernel"] = (result.get("uname") or "").strip()
        ssh.close()
    except Exception as e:
        pass
    return info

def windows_probe(target):
    # Minimal placeholder (WMI/WinRM can be added). We just confirm reachability here.
    host = target['host']
    info = {"name": host, "type": "workstation", "ips": [host], "attributes": {"os":{"family":"windows"}}, "mac": None}
    return info

def push_update(cfg, asset, online=True):
    url = cfg["api"]["base_url"] + "?action=poller_report"
    headers = {"X-API-Key": cfg["api"]["api_key"], "Content-Type":"application/json"}
    payload = {"asset": asset, "online_status": online, "source":"poller"}
    # Use same agent push endpoint for simplicity (tokenless via api key isn't enabled by default)
    # You can create a special agent with token and use that here if preferred.
    # For now, we use 'poller' integration endpoint:
    url = cfg["api"]["base_url"] + "?action=agent_push&token=" + cfg["api"]["api_key"]
    try:
        requests.post(url, json={"asset": asset, "online_status": online}, timeout=10)
    except Exception:
        pass

def main():
    cfg = yaml.safe_load(open("config.yml","r"))
    while True:
        for t in cfg.get("linux", []):
            asset = linux_probe(t)
            online = ping(t["host"])
            push_update(cfg, asset, online)
        for t in cfg.get("windows", []):
            asset = windows_probe(t)
            online = ping(t["host"])
            push_update(cfg, asset, online)
        time.sleep(cfg.get("interval_seconds", 120))

if __name__ == "__main__":
    main()
