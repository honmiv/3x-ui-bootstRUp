#!/usr/bin/env python3
"""Subscription server: proxy + web interface.

GET /<SECRET_SUB_PATH>               - web page with client cards (links + QR).
GET /<SECRET_SUB_PATH>?raw=1         - plain text list of target subscription URLs
                                       (also served for non-browser clients).
GET /<SECRET_SUB_PATH>/<client_name> - subscription content fetched from the
                                       node's subscription URL.
POST /<SECRET_SUB_PATH>/api/override - set/clear a custom vless:// override for a
                                       client. Body: {"client": "...", "value": "..."}.
                                       value="" clears the override. Values are stored
                                       in FORCE_FILE as base64.
GET  /<SECRET_SUB_PATH>/api/logs     - real-time log stream (SSE) tailing LOG_FILE,
                                       the same output docker logs -f subs-server shows.

The client name is looked up in the node registry (nodes.json):
  - each node has an id, a display name, a subscription base URL and a
    client list; clients are routed to the node that owns them.
  - a legacy subs.yml (two lists: proxy and freedom) is only read once to
    seed nodes.json when the registry is missing or empty.

Env vars:
  FORCE_FILE      path to force-subs.yml overrides (default: force-subs.yml)
  NODES_FILE      path to nodes.json registry (default: nodes.json)
  LOG_FILE        path to a log file tailed by the /api/logs SSE stream
                  (default: sub-server.log)
  SECRET_SUB_PATH path prefix from the domain root (default: subs)
  RUSSIAN_SUB_URL subscription URL of the Russian node (fallback only)
  FOREIGN_SUB_URL subscription URL of the non-Russian node (fallback only)
  PUBLIC_URL      optional public base URL (e.g. https://vpn.example.com);
                  if unset, derived from the request Host/X-Forwarded-* headers
  HOST            listen address (default: 0.0.0.0)
  PORT            listen port (default: 8080)
"""

import base64
import hmac
import html
import json
import logging
import os
import queue
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import yaml
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from urllib.parse import unquote

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("sub-server")

LOG_LINE_RE = re.compile(r"^(\S+ \S+) (\w+) (.*)$")
LOG_HISTORY_LINES = 200
LOG_HISTORY_BYTES = 256 * 1024

DATABASE_FILE = os.environ.get("DATABASE_FILE", "subs.yml")
FORCE_FILE = os.environ.get("FORCE_FILE", "force-subs.yml")
NODES_FILE = os.environ.get("NODES_FILE", "nodes.json")
LOG_FILE = os.environ.get("LOG_FILE", "sub-server.log")
SECRET_SUB_PATH = os.environ.get("SECRET_SUB_PATH", "subs").strip("/")
RUSSIAN_SUB_URL = os.environ.get("RUSSIAN_SUB_URL", "")
FOREIGN_SUB_URL = os.environ.get("FOREIGN_SUB_URL", "")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").strip().strip("/")
ADMIN_USER = os.environ.get("ADMIN_USER", "").strip()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()
AUTH_SESSION_SECRET = os.environ.get("AUTH_SESSION_SECRET", "").strip() or secrets.token_hex(32)
SESSION_TTL_SECONDS = int(os.environ.get("AUTH_SESSION_TTL", "43200"))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))

GROUP_LABELS = {
    "proxy": "Proxy (РФ)",
    "freedom": "Freedom (зарубежье)",
    "force": "Кастом (force-subs.yml)",
}

NODE_TYPE_LABELS = {
    "proxy": "Proxy",
    "freedom": "Freedom",
    "custom": "Кастом",
}


def extract_domain_from_url(url):
    if not url:
        return ""
    u = re.sub(r"^[a-zA-Z]+://", "", url.strip())
    return u.split("/")[0].split(":")[0].strip()


def get_node_type(node):
    if not node or not isinstance(node, dict):
        return "proxy"
    t = str(node.get("type") or "").strip().lower()
    if t in NODE_TYPE_LABELS:
        return t
    nid = str(node.get("id") or "").lower()
    nname = str(node.get("name") or "").lower()
    if "proxy" in nid or "proxy" in nname or "рф" in nname:
        return "proxy"
    if "freedom" in nid or "freedom" in nname or "зарубеж" in nname:
        return "freedom"
    return "proxy"


def get_node_type_label(node):
    return NODE_TYPE_LABELS.get(get_node_type(node), "Proxy")

NODES = []
FORCE_SUBS = {}
DATA_LOCK = threading.Lock()
ACTIVITY_LOCK = threading.Lock()
LOGIN_LOCK = threading.Lock()
LOGIN_ATTEMPTS = {}  # ip -> {"count": int, "lockout_until": float, "last_attempt": float}

WEB_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "web")

def _load_web_template(name):
    with open(os.path.join(WEB_TEMPLATE_DIR, name), encoding="utf-8") as f:
        return f.read()


PAGE_TEMPLATE = _load_web_template("dashboard.html")

LOGIN_TEMPLATE = _load_web_template("login.html")


def setup_file_logging():
    """Mirror all sub-server logs to a file (the web UI tails this file).

    stdout (captured by ``docker logs -f subs-server``) and the log file stay
    in sync because the "sub-server" logger propagates to the root handler
    while also writing to LOG_FILE.
    """
    try:
        directory = os.path.dirname(os.path.abspath(LOG_FILE))
        os.makedirs(directory, exist_ok=True)
        handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        log.addHandler(handler)
    except OSError as exc:
        log.warning("could not open log file %s: %s", LOG_FILE, exc)


# Real-time per-client activity (last sync status), pushed to the web UI via
# the /api/logs SSE stream as `event: activity`.
CLIENT_ACTIVITY: dict = {}
ACTIVITY_SUBSCRIBERS: set = set()
ACTIVITY_LOCK = threading.Lock()
# Incremented on every admin status reset; open SSE streams use it to reset
# their log-file position after the file is truncated.
LOG_RESET_EVENT = 0


def reset_sync_statuses():
    """Clear all per-client sync statuses (memory + log file).

    ``CLIENT_ACTIVITY`` is emptied in-place so already-connected SSE streams
    pick up the change, and LOG_FILE is truncated so the statuses do not come
    back after a container restart (load_past_activity_from_logs reads it at
    startup).
    """
    global LOG_RESET_EVENT
    with ACTIVITY_LOCK:
        CLIENT_ACTIVITY.clear()
    try:
        with open(LOG_FILE, "w", encoding="utf-8"):
            pass
    except OSError as exc:
        log.warning("could not truncate %s: %s", LOG_FILE, exc)
    LOG_RESET_EVENT += 1
    log.info("sync statuses reset by admin")


def get_client_sync_state(client):
    with ACTIVITY_LOCK:
            activity = CLIENT_ACTIVITY.get(client)
    if not activity or not activity.get("time"):
        return "never"
    ts = activity.get("timestamp")
    if ts is None and activity.get("time"):
        try:
            ts = time.mktime(time.strptime(activity["time"], "%Y-%m-%d %H:%M:%S"))
        except Exception:
            ts = 0
    now = time.time()
    if ts and (now - ts <= 86400):
        return "recent"
    return "ever"


def _record_activity(client, status, bytes_, node, node_name, source, timestamp=None, ts_str=None):
    now_ts = timestamp if timestamp is not None else time.time()
    time_str = ts_str if ts_str is not None else time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ts))
    activity = {
        "client": client,
        "time": time_str,
        "timestamp": now_ts,
        "status": status,
        "bytes": bytes_,
        "node": node,
        "node_name": node_name,
        "source": source,
    }
    with ACTIVITY_LOCK:
        CLIENT_ACTIVITY[client] = activity
    payload = json.dumps(activity, ensure_ascii=False)
    with ACTIVITY_LOCK:
        for stream_queue in list(ACTIVITY_SUBSCRIBERS):
            try:
                stream_queue.put_nowait(payload)
            except Exception:
                pass


def load_past_activity_from_logs(path):
    if not os.path.exists(path):
        return
    sync_re = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+\w+\s+(200|404|502)\s+([^\s\(]+)(?:\s+\((.*)\))?\s*(?:->|<-\s*(\S+))?\s*(?:\(?(\d+)\s*bytes\)?)?")
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                m = sync_re.search(line)
                if m:
                    ts_str, status_str, client, group, url, bytes_str = m.groups()
                    try:
                        ts = time.mktime(time.strptime(ts_str, "%Y-%m-%d %H:%M:%S"))
                    except Exception:
                        ts = 0
                    status = int(status_str)
                    bytes_ = int(bytes_str) if bytes_str else 0
                    node_name = GROUP_LABELS.get("force") if group == "force" else group
                    with ACTIVITY_LOCK:
                        CLIENT_ACTIVITY[client] = {
                            "client": client,
                            "time": ts_str,
                            "timestamp": ts,
                            "status": status,
                            "bytes": bytes_,
                            "node": group if group != "force" else None,
                            "node_name": node_name,
                            "source": "force" if group == "force" else "node",
                        }
    except Exception as exc:
        log.warning("could not read past activity from log file: %s", exc)


def load_subs(path):
    """Load the legacy client database (subs.yml) with PyYAML.

    Expected structure (generated by older setup.sh versions):

        proxy:
          - client1
        freedom:
          - client2

    Only the ``proxy`` and ``freedom`` lists are read; anything else is ignored.

    LEGACY: subs.yml is only used to seed nodes.json when the registry is
    missing or empty. Remove once all existing deployments have migrated.
    """
    subs = {"proxy": [], "freedom": []}
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except (OSError, ValueError, yaml.YAMLError) as exc:
        log.warning("failed to parse %s: %s; using empty legacy configuration", path, exc)
        return subs
    if not isinstance(raw, dict):
        return subs
    for group in subs:
        clients = raw.get(group, [])
        if isinstance(clients, list):
            subs[group] = [str(client).strip() for client in clients if str(client).strip()]
    return subs


def default_nodes(legacy_subs=None):
    nodes = []
    legacy_subs = legacy_subs or {"proxy": [], "freedom": []}
    ru_url = RUSSIAN_SUB_URL.rstrip("/")
    if ru_url and not ru_url.startswith(("http://", "https://")):
        ru_url = "https://" + ru_url
    fr_url = FOREIGN_SUB_URL.rstrip("/")
    if fr_url and not fr_url.startswith(("http://", "https://")):
        fr_url = "https://" + fr_url

    ru_domain = os.environ.get("PROXY_DOMAIN", "").strip() or extract_domain_from_url(ru_url) or "proxy"
    fr_domain = os.environ.get("FREEDOM_DOMAIN", "").strip() or extract_domain_from_url(fr_url) or "freedom"

    for node_id, node_type, name, url, group in (
        ("proxy", "proxy", ru_domain, ru_url, "proxy"),
        ("freedom", "freedom", fr_domain, fr_url, "freedom"),
    ):
        url = url.rstrip("/")
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        if url or legacy_subs[group]:
            nodes.append({
                "id": node_id,
                "type": node_type,
                "name": name,
                "url": url,
                "clients": list(legacy_subs[group]),
                "supports_json": True,
            })
    return nodes


def load_nodes(path, legacy_subs=None):
    if not os.path.exists(path):
        return default_nodes(legacy_subs)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        log.warning("failed to load %s: %s; using node configuration from environment", path, exc)
        return default_nodes(legacy_subs)
    if not isinstance(data, list):
        return default_nodes(legacy_subs)
    result = []
    for item in data:
        if not isinstance(item, dict) or not item.get("id") or not item.get("name") or not item.get("url"):
            continue
        clients = item.get("clients", [])
        if not isinstance(clients, list):
            clients = []
        json_clients = item.get("json_clients", [])
        if not isinstance(json_clients, list):
            json_clients = []
        url = str(item["url"]).strip().rstrip("/")
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url

        node_type = get_node_type(item)
        name = str(item["name"]).strip()
        if (not name or name.lower() in ("proxy", "freedom", "proxy (рф)", "freedom (зарубежье)")) and url:
            domain = extract_domain_from_url(url)
            if domain:
                name = domain

        result.append({
            "id": str(item["id"]),
            "type": node_type,
            "name": name,
            "url": url,
            "clients": [str(client).strip() for client in clients if str(client).strip()],
            "json_clients": [str(client).strip() for client in json_clients if str(client).strip()],
            "supports_json": bool(item.get("supports_json", True)),
        })
    return result or default_nodes(legacy_subs)


def save_nodes(nodes=None):
    nodes = NODES if nodes is None else nodes
    directory = os.path.dirname(os.path.abspath(NODES_FILE))
    os.makedirs(directory, exist_ok=True)
    # NODES_FILE is bind-mounted by Docker, so replace() would fail on the
    # mount point itself. The file is tiny and is protected by the admin API.
    with open(NODES_FILE, "w", encoding="utf-8") as f:
        json.dump(nodes, f, ensure_ascii=False, indent=2)
        f.write("\n")


def nodes_file_is_empty(path):
    """Return whether the node file is missing or contains no JSON data.

    setup.sh creates nodes.json with the full registry for new installations.
    A missing or empty file is reseeded from the environment URLs, optionally
    migrated from the legacy subs.yml.
    """
    if not os.path.exists(path):
        return True
    try:
        with open(path, encoding="utf-8") as f:
            return not f.read().strip()
    except OSError:
        return False


def all_clients():
    return {client for node in NODES for client in node.get("clients", [])}


def find_client_node(client):
    return next((node for node in NODES if client in node.get("clients", [])), None)


def load_force_subs(path):
    """Load override subscriptions from force-subs.yml (map of client -> value)."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except (OSError, ValueError, yaml.YAMLError) as exc:
        log.warning("failed to parse %s: %s; ignoring overrides", path, exc)
        return {}
    if not isinstance(raw, dict):
        log.warning("%s is not a mapping; ignoring overrides", path)
        return {}
    force = {}
    for key, value in raw.items():
        key = str(key).strip()
        value = str(value).strip()
        if key and value:
            force[key] = value
    return force


def encode_override_value(value):
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def decode_override_value(raw):
    raw = (raw or "").strip()
    try:
        data = base64.b64decode(raw, validate=True)
    except Exception:
        return raw
    if base64.b64encode(data).decode("ascii").rstrip("=") != raw.rstrip("="):
        return raw
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return raw


def save_force_subs(force=None):
    force = FORCE_SUBS if force is None else force
    directory = os.path.dirname(os.path.abspath(FORCE_FILE))
    os.makedirs(directory, exist_ok=True)
    header = (
        "# force-subs.yml\n"
        "# Переопределение подписки для конкретного клиента (значение закодировано в base64).\n"
        "# Формат: <client>: <base64-контент подписки>\n"
    )
    with open(FORCE_FILE, "w", encoding="utf-8") as f:
        f.write(header)
        yaml.safe_dump(force, f, allow_unicode=True, sort_keys=True, default_flow_style=False)


FORWARD_EXCLUDED_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "date",
    "server",
}



def transform_configs(all_configs, routing_header_b64, client_name):
    if not all_configs:
        return {}
        
    base_config = all_configs[0]
    is_multi = len(all_configs) > 1
    
    final_config = {
        "dns": base_config.get("dns", {}),
        "inbounds": base_config.get("inbounds", []),
        "log": base_config.get("log", {"loglevel": "warning"}),
        "policy": base_config.get("policy", {}),
        "routing": base_config.get("routing", {}),
        "stats": base_config.get("stats", {})
    }
    final_config["remarks"] = client_name
    
    target_tag_key = "outboundTag"
    target_tag_val = "proxy"
    proxy_tags = []
    
    if is_multi:
        proxy_outbounds = []
        for idx, conf in enumerate(all_configs):
            outs = conf.get("outbounds", [])
            for out in outs:
                if out.get("tag") == "proxy" or out.get("protocol") in ("vless", "vmess", "trojan", "shadowsocks"):
                    addr = out.get("settings", {}).get("address", f"node{idx}")
                    net = out.get("streamSettings", {}).get("network", "tcp")
                    new_tag = f"proxy-{addr.split('.')[0]}-{net}-{idx}"
                    out["tag"] = new_tag
                    proxy_outbounds.append(out)
                    proxy_tags.append(new_tag)
                    
        final_outbounds = proxy_outbounds + [
            {"protocol": "freedom", "settings": {"domainStrategy": "AsIs", "noises": [], "redirect": ""}, "tag": "direct"},
            {"protocol": "blackhole", "settings": {"response": {"type": "http"}}, "tag": "block"}
        ]
        final_config["outbounds"] = final_outbounds
        final_config["observatory"] = {
            "subjectSelector": proxy_tags,
            "probeURL": "https://cp.cloudflare.com/generate_204",
            "probeInterval": "10s",
            "enableConcurrent": True
        }
        target_tag_key = "balancerTag"
        target_tag_val = "lb"
    else:
        final_config["outbounds"] = base_config.get("outbounds", [])
        
    if routing_header_b64:
        try:
            import json, base64
            header_val = routing_header_b64
            if "happ://routing/onadd/" in header_val:
                header_val = header_val.split("happ://routing/onadd/")[-1]
            elif "://" in header_val:
                header_val = header_val.split("://")[-1].split("/")[-1]
                
            routing_data = json.loads(base64.b64decode(header_val).decode('utf-8'))
            
            dns = {
                "queryStrategy": "UseIP",
                "servers": [],
                "tag": "dns_out"
            }
            if routing_data.get("DnsHosts"):
                dns["hosts"] = routing_data["DnsHosts"]
                
            if routing_data.get("RemoteDns"):
                dns["servers"].append({"address": routing_data["RemoteDns"], "skipFallback": False})
                
            if routing_data.get("DomesticDns"):
                dom_dns = {"address": routing_data["DomesticDns"]}
                dom_domains = []
                if "domain:ru" in routing_data.get("DirectSites", []):
                    dom_domains.append("domain:ru")
                if "domain:xn--p1ai" in routing_data.get("DirectSites", []):
                    dom_domains.append("domain:xn--p1ai")
                if "geosite:category-ru" in routing_data.get("DirectSites", []):
                    dom_domains.append("geosite:category-ru")
                if dom_domains:
                    dom_dns["domains"] = dom_domains
                dns["servers"].append(dom_dns)
                
            final_config["dns"] = dns
            
            rules = []
            
            if routing_data.get("BlockSites"):
                rules.append({"type": "field", "outboundTag": "block", "domain": routing_data["BlockSites"]})
            if routing_data.get("BlockIp"):
                rules.append({"type": "field", "outboundTag": "block", "ip": routing_data["BlockIp"]})
                
            if routing_data.get("ProxySites"):
                rules.append({"type": "field", target_tag_key: target_tag_val, "domain": routing_data["ProxySites"]})
            if routing_data.get("ProxyIp"):
                rules.append({"type": "field", target_tag_key: target_tag_val, "ip": routing_data["ProxyIp"]})
                
            if routing_data.get("DirectSites"):
                rules.append({"type": "field", "outboundTag": "direct", "domain": routing_data["DirectSites"]})
            if routing_data.get("DirectIp"):
                rules.append({"type": "field", "outboundTag": "direct", "ip": routing_data["DirectIp"]})
                
            rules.append({"network": "tcp,udp", "type": "field", target_tag_key: target_tag_val})
            
            final_routing = {
                "domainStrategy": routing_data.get("DomainStrategy", "IPIfNonMatch"),
                "rules": rules
            }
            if is_multi:
                final_routing["balancers"] = [{
                    "tag": "lb", 
                    "selector": proxy_tags, 
                    "strategy": {
                        "type": "leastLoad",
                        "settings": {"expected": 1, "maxRTT": "5s", "baselines": ["50ms", "150ms", "300ms", "500ms", "1s"], "tolerance": 0.1}
                    }
                }]
            final_config["routing"] = final_routing

        except Exception as e:
            log.error("Error parsing routing header: %s", e)
            if is_multi:
                final_config["routing"] = {
                    "domainStrategy": "IPIfNonMatch",
                    "balancers": [{ "tag": "lb", "selector": proxy_tags, "strategy": {"type": "leastLoad","settings": {"expected": 1, "maxRTT": "5s", "baselines": ["50ms", "150ms", "300ms", "500ms", "1s"], "tolerance": 0.1}}}],
                    "rules": [{"network": "tcp,udp", "balancerTag": "lb", "type": "field"}]
                }
            else:
                final_config["routing"] = {
                    "domainStrategy": "IPIfNonMatch",
                    "rules": [{"network": "tcp,udp", "outboundTag": "proxy", "type": "field"}]
                }
    else:
        # No routing header case
        if is_multi:
            final_config["routing"] = {
                "domainStrategy": "IPIfNonMatch",
                "balancers": [{ "tag": "lb", "selector": proxy_tags, "strategy": {"type": "leastLoad","settings": {"expected": 1, "maxRTT": "5s", "baselines": ["50ms", "150ms", "300ms", "500ms", "1s"], "tolerance": 0.1}}}],
                "rules": [{"network": "tcp,udp", "balancerTag": "lb", "type": "field"}]
            }

    return final_config

def fetch_subscription(url, user_agent=None, extra_headers=None):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    req_headers = {}
    if user_agent:
        req_headers["User-Agent"] = user_agent
    else:
        req_headers["User-Agent"] = "sub-server/1.0"
    if extra_headers:
        req_headers.update(extra_headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read(), resp.headers


class Handler(BaseHTTPRequestHandler):
    def _enforce_https(self):
        proto = self.headers.get("X-Forwarded-Proto", "").split(",")[0].strip().lower()
        if proto == "http":
            host = (self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "").strip()
            if host:
                self.send_response(301)
                self.send_header("Location", f"https://{host}{self.path}")
                self.end_headers()
                return False
            self.send_error(403, "HTTPS required")
            return False
        return True

    def _cookie_name(self):
        return f"sub_session_{SECRET_SUB_PATH}"

    def _parse_cookies(self):
        raw = self.headers.get("Cookie", "")
        cookies = {}
        for part in raw.split(";"):
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            cookies[k.strip()] = urllib.parse.unquote(v.strip())
        return cookies

    def _safe_next_path(self, next_path):
        val = (next_path or "").strip()
        if not val.startswith("/"):
            return f"/{SECRET_SUB_PATH}"
        # Prevent open redirects to external URLs.
        if not val.startswith(f"/{SECRET_SUB_PATH}"):
            return f"/{SECRET_SUB_PATH}"
        return val

    def _build_session_value(self, expires_ts):
        payload = f"{ADMIN_USER}:{expires_ts}"
        sig = hmac.new(AUTH_SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), "sha256").hexdigest()
        return f"{expires_ts}.{sig}"

    def _validate_session_value(self, token):
        if not token or "." not in token or not AUTH_SESSION_SECRET:
            return False
        ts_raw, sig = token.split(".", 1)
        if not ts_raw.isdigit():
            return False
        expires_ts = int(ts_raw)
        if expires_ts <= int(time.time()):
            return False
        expected = self._build_session_value(expires_ts).split(".", 1)[1]
        return hmac.compare_digest(sig, expected)

    def _set_session_cookie(self, max_age=SESSION_TTL_SECONDS):
        expires_ts = int(time.time()) + max(60, max_age)
        token = self._build_session_value(expires_ts)
        cookie = f"{self._cookie_name()}={urllib.parse.quote(token)}; Path=/{SECRET_SUB_PATH}; HttpOnly; SameSite=Lax; Max-Age={max(60, max_age)}"
        proto = self.headers.get("X-Forwarded-Proto", "").lower()
        if proto == "https":
            cookie += "; Secure"
        self.send_header("Set-Cookie", cookie)

    def _clear_session_cookie(self):
        cookie = f"{self._cookie_name()}=; Path=/{SECRET_SUB_PATH}; HttpOnly; SameSite=Lax; Max-Age=0"
        proto = self.headers.get("X-Forwarded-Proto", "").lower()
        if proto == "https":
            cookie += "; Secure"
        self.send_header("Set-Cookie", cookie)

    def _verify_login_password(self, user, password):
        return hmac.compare_digest(user or "", ADMIN_USER) and hmac.compare_digest(password or "", ADMIN_PASSWORD)

    def _basic_header_is_valid(self):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8")
        except Exception:
            return False
        user, _, password = decoded.partition(":")
        return self._verify_login_password(user, password)

    def _is_admin_authenticated(self):
        if not ADMIN_USER or not ADMIN_PASSWORD:
            return True
        cookies = self._parse_cookies()
        if self._validate_session_value(cookies.get(self._cookie_name(), "")):
            return True
        return self._basic_header_is_valid()

    def _require_auth(self, api=False):
        if self._is_admin_authenticated():
            return True
        log.info("401 unauthorized: %s", self.path)
        if api:
            self._send_json(401, {"ok": False, "error": "authentication required"})
            return False

        next_path = self._safe_next_path(self.path)
        login_url = f"/{SECRET_SUB_PATH}/login?next={urllib.parse.quote(next_path, safe='/%?=&') }"
        self.send_response(302)
        self.send_header("Location", login_url)
        self.end_headers()
        return False

    def _render_login_page(self, error_message="", next_path=""):
        safe_next = self._safe_next_path(next_path)
        error_html = ""
        if error_message:
            error_html = f'<div class="error">{html.escape(error_message)}</div>'
        body = (
            LOGIN_TEMPLATE
            .replace("__ERROR_BLOCK__", error_html)
            .replace("__NEXT__", html.escape(safe_next, quote=True))
            .replace("__LOGIN_ACTION__", f"/{SECRET_SUB_PATH}/login")
            .encode("utf-8")
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _client_ip(self):
        xff = self.headers.get("X-Forwarded-For", "").strip()
        if xff:
            return xff.split(",")[0].strip()
        return self.client_address[0] if self.client_address else "unknown"

    def _handle_login_post(self):
        ip = self._client_ip()
        now = time.time()

        with LOGIN_LOCK:
            record = LOGIN_ATTEMPTS.get(ip)
            if record and record.get("lockout_until", 0) > now:
                remaining = int(record["lockout_until"] - now)
                self._render_login_page(f"Слишком много неудачных попыток. Попробуйте через {remaining} сек.", self._safe_next_path(f"/{SECRET_SUB_PATH}"))
                return

        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length).decode("utf-8", errors="ignore") if length else ""
        form = urllib.parse.parse_qs(raw, keep_blank_values=True)
        user = (form.get("user", [""])[0] or "").strip()
        password = form.get("password", [""])[0] or ""
        next_path = self._safe_next_path(form.get("next", [f"/{SECRET_SUB_PATH}"])[0])

        if not self._verify_login_password(user, password):
            with LOGIN_LOCK:
                rec = LOGIN_ATTEMPTS.setdefault(ip, {"count": 0, "lockout_until": 0, "last_attempt": now})
                if now - rec.get("last_attempt", 0) > 300:
                    rec["count"] = 0
                rec["count"] += 1
                rec["last_attempt"] = now
                if rec["count"] >= 5:
                    rec["lockout_until"] = now + 300  # 5 min lockout
                    rec["count"] = 0
            self._render_login_page("Неверный логин или пароль.", next_path)
            return

        with LOGIN_LOCK:
            LOGIN_ATTEMPTS.pop(ip, None)

        self.send_response(302)
        self._set_session_cookie()
        self.send_header("Location", next_path)
        self.end_headers()

    def _handle_logout(self):
        self.send_response(302)
        self._clear_session_cookie()
        self.send_header("Location", f"/{SECRET_SUB_PATH}/login")
        self.end_headers()

    def do_GET(self):
        if not self._enforce_https():
            return
        path = unquote(self.path.split("?", 1)[0]).strip("/")
        if path == f"{SECRET_SUB_PATH}/login":
            if not ADMIN_USER or not ADMIN_PASSWORD:
                self.send_response(302)
                self.send_header("Location", f"/{SECRET_SUB_PATH}")
                self.end_headers()
                return
            params = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            next_path = params.get("next", [f"/{SECRET_SUB_PATH}"])[0]
            self._render_login_page("", next_path)
            return

        if path == f"{SECRET_SUB_PATH}/logout":
            self._handle_logout()
            return

        if path == f"{SECRET_SUB_PATH}/api/logs":
            if not self._require_auth(api=True):
                return
            self._stream_logs()
            return

        parts = path.split("/")
        if len(parts) == 1 and parts[0] == SECRET_SUB_PATH:
            if not self._require_auth():
                return
            if self._wants_html():
                self._list_html()
            else:
                self._list_subscriptions()
            return
        if len(parts) == 3 and parts[0] == SECRET_SUB_PATH and parts[1] == "json":
            client = parts[2]
            is_json = True
        elif len(parts) == 2 and parts[0] == SECRET_SUB_PATH:
            client = parts[1]
            is_json = False
        else:
            log.warning("404 unknown path: %s", self.path)
            self.send_error(404)
            return
        if client in FORCE_SUBS:
            body = FORCE_SUBS[client].encode("utf-8")
            log.info("200 %s (force) -> %d bytes", client, len(body))
            _record_activity(client, 200, len(body), None, GROUP_LABELS["force"], "force")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        node = find_client_node(client)
        if not node:
            log.warning("404 unknown client: %s", client)
            _record_activity(client, 404, 0, None, None, None)
            self.send_error(404)
            return
        base_url = node["url"]
        group = node["id"]
        node_name = node["name"]
        if not base_url:
            log.error("502 no subscription URL configured for node '%s' (client %s)", node_name, client)
            _record_activity(client, 502, 0, group, node_name, "node")
            self.send_error(502)
            return
        quoted_client = urllib.parse.quote(client, safe='')
        client_ua = self.headers.get("User-Agent")
        extra_headers = {}
        for h in ("Accept", "Accept-Language"):
            val = self.headers.get(h)
            if val:
                extra_headers[h] = val

        if is_json:
            additional_json_nodes = [n for n in NODES if client in n.get("json_clients", [])]
            all_nodes = [node] + additional_json_nodes
            merged_json = []
            routing_header_b64 = None
            
            primary_upstream_headers = None
            for idx, n in enumerate(all_nodes):
                n_url = f"{n['url'].rstrip('/')}/json/{quoted_client}"
                try:
                    b, up_headers = fetch_subscription(n_url, user_agent=client_ua, extra_headers=extra_headers)
                    # grab routing header from primary node
                    if idx == 0 and up_headers:
                        primary_upstream_headers = up_headers
                        for k, v in up_headers.items():
                            if k.lower() == "routing":
                                routing_header_b64 = v
                                break
                    import json
                    data = json.loads(b.decode("utf-8"))
                    if isinstance(data, list):
                        merged_json.extend(data)
                    else:
                        merged_json.append(data)
                except Exception as e:
                    log.error("Failed to fetch JSON for %s from node %s: %s", client, n['name'], e)
            
            final_config = transform_configs(merged_json, routing_header_b64, client)
            body = json.dumps(final_config, ensure_ascii=False, indent=2).encode("utf-8")
            log.info("200 %s (transformed JSON %d nodes) <- (%d bytes)", client, len(all_nodes), len(body))
            _record_activity(client, 200, len(body), group, node_name, "node")
            self.send_response(200)
            
            if primary_upstream_headers:
                for key, value in primary_upstream_headers.items():
                    kl = key.lower()
                    if kl in FORWARD_EXCLUDED_HEADERS or kl == "content-type" or kl == "content-length":
                        continue
                    self.send_header(key, value)

            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        url = f"{base_url.rstrip('/')}/{quoted_client}"

        try:
            body, upstream_headers = fetch_subscription(url, user_agent=client_ua, extra_headers=extra_headers)
        except urllib.error.HTTPError as e:
            log.error("502 fetch failed for %s (%s): HTTP %s %s (url=%s)", client, node_name, e.code, e.reason, url)
            _record_activity(client, 502, 0, group, node_name, "node")
            self.send_error(502)
            return
        except urllib.error.URLError as e:
            log.error("502 fetch failed for %s (%s): %s (url=%s)", client, node_name, e.reason, url)
            _record_activity(client, 502, 0, group, node_name, "node")
            self.send_error(502)
            return
        except Exception as e:
            log.error("502 fetch failed for %s (%s): %r (url=%s)", client, node_name, e, url)
            _record_activity(client, 502, 0, group, node_name, "node")
            self.send_error(502)
            return
        log.info("200 %s (%s) <- %s (%d bytes)", client, node_name, url, len(body))
        _record_activity(client, 200, len(body), group, node_name, "node")
        self.send_response(200)
        has_content_type = False
        if upstream_headers:
            for key, value in upstream_headers.items():
                if key.lower() in FORWARD_EXCLUDED_HEADERS:
                    continue
                if key.lower() == "content-type":
                    has_content_type = True
                self.send_header(key, value)
        if not has_content_type:
            self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _query_params(self):
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        return set(p.split("=")[0].strip() for p in query.split("&") if p.strip())

    def do_POST(self):
        if not self._enforce_https():
            return
        global FORCE_SUBS, NODES
        path = unquote(self.path.split("?", 1)[0]).strip("/")
        if path == f"{SECRET_SUB_PATH}/login":
            self._handle_login_post()
            return
        if path == f"{SECRET_SUB_PATH}/logout":
            self._handle_logout()
            return

        api_paths = {
            f"{SECRET_SUB_PATH}/api/override",
            f"{SECRET_SUB_PATH}/api/client",
            f"{SECRET_SUB_PATH}/api/node",
            f"{SECRET_SUB_PATH}/api/reset",
        }
        if path not in api_paths:
            log.warning("404 unknown POST path: %s", self.path)
            self.send_error(404)
            return
        if not self._require_auth(api=True):
            return
        if path == f"{SECRET_SUB_PATH}/api/reset":
            reset_sync_statuses()
            self._send_json(200, {"ok": True})
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("JSON must be an object")
        except Exception:
            self._send_json(400, {"ok": False, "error": "невалидный JSON"})
            return

        with DATA_LOCK:
            if path == f"{SECRET_SUB_PATH}/api/client":
                action = (data.get("action") or "").strip()
                client = (data.get("client") or "").strip()
                reserved = {"login", "logout", "api", "logs", "static"}
                if not client or any(char in client for char in "\r\n:/") or client in reserved:
                    self._send_json(400, {"ok": False, "error": "некорректное или зарезервированное имя клиента"})
                    return
                if action == "add":
                    node = next((item for item in NODES if item["id"] == (data.get("node") or "")), None)
                    if not node:
                        self._send_json(400, {"ok": False, "error": "нода не найдена"})
                        return
                    if client in all_clients() or client in FORCE_SUBS:
                        self._send_json(400, {"ok": False, "error": "клиент с таким именем уже существует"})
                        return
                    node.get("clients", []).append(client)
                    if "additional_json_nodes" in data:
                        for n_id in data["additional_json_nodes"]:
                            target = next((n for n in NODES if n["id"] == n_id), None)
                            if target:
                                if "json_clients" not in target:
                                    target["json_clients"] = []
                                if client not in target["json_clients"]:
                                    target["json_clients"].append(client)
                elif action == "delete":
                    node = find_client_node(client)
                    if not node and client not in FORCE_SUBS:
                        self._send_json(400, {"ok": False, "error": "клиент не найден"})
                        return
                    for n in NODES:
                        while client in n.get("clients", []):
                            n["clients"].remove(client)
                    if client in FORCE_SUBS:
                        new_force = dict(FORCE_SUBS)
                        new_force.pop(client, None)
                        try:
                            save_force_subs(new_force)
                        except OSError as exc:
                            self._send_json(500, {"ok": False, "error": f"не удалось удалить override: {exc}"})
                            return
                        FORCE_SUBS = new_force
                elif action == "add_json_node":
                    node_id = (data.get("node") or "").strip()
                    target_node = next((n for n in NODES if n["id"] == node_id), None)
                    if not target_node:
                        self._send_json(400, {"ok": False, "error": "нода не найдена"})
                        return
                    if "json_clients" not in target_node:
                        target_node["json_clients"] = []
                    if client not in target_node["json_clients"]:
                        target_node["json_clients"].append(client)
                        try:
                            save_nodes()
                        except Exception as e:
                            self._send_json(500, {"ok": False, "error": str(e)})
                            return
                    self._send_json(200, {"ok": True})
                elif action == "remove_json_node":
                    node_id = (data.get("node") or "").strip()
                    target_node = next((n for n in NODES if n["id"] == node_id), None)
                    if not target_node:
                        self._send_json(400, {"ok": False, "error": "нода не найдена"})
                        return
                    if "json_clients" in target_node and client in target_node["json_clients"]:
                        target_node["json_clients"].remove(client)
                        try:
                            save_nodes()
                        except Exception as e:
                            self._send_json(500, {"ok": False, "error": str(e)})
                            return
                    self._send_json(200, {"ok": True})
                elif action == "edit":
                    new_name = (data.get("new_name") or "").strip()
                    target_id = (data.get("node") or "").strip()
                    if not new_name or any(char in new_name for char in "\r\n:/"):
                        self._send_json(400, {"ok": False, "error": "некорректное имя клиента"})
                        return
                    cur_node = find_client_node(client)
                    is_force = client in FORCE_SUBS
                    if not cur_node and not is_force:
                        self._send_json(400, {"ok": False, "error": "клиент не найден"})
                        return
                    target_node = None
                    if target_id:
                        target_node = next((item for item in NODES if item["id"] == target_id), None)
                        if not target_node:
                            self._send_json(400, {"ok": False, "error": "нода не найдена"})
                            return
                    other_clients = {c for n in NODES for c in n.get("clients", []) if c != client}
                    if new_name != client and (new_name in other_clients or (new_name in FORCE_SUBS and not is_force)):
                        self._send_json(400, {"ok": False, "error": "клиент с таким именем уже существует"})
                        return
                    if new_name == client and cur_node is target_node:
                        self._send_json(200, {"ok": True})
                        return
                    if new_name != client and client in FORCE_SUBS:
                        new_force = dict(FORCE_SUBS)
                        new_force[new_name] = new_force.pop(client)
                        try:
                            save_force_subs(new_force)
                        except OSError as exc:
                            self._send_json(500, {"ok": False, "error": f"не удалось обновить override: {exc}"})
                            return
                        FORCE_SUBS = new_force
                    for n in NODES:
                        while client in n.get("clients", []):
                            n["clients"].remove(client)
                    if target_node:
                        if new_name not in target_node.get("clients", []):
                            target_node.get("clients", []).append(new_name)
                else:
                    self._send_json(400, {"ok": False, "error": "неизвестное действие"})
                    return
                try:
                    save_nodes()
                except OSError as exc:
                    self._send_json(500, {"ok": False, "error": f"не удалось сохранить ноды: {exc}"})
                    return
                self._send_json(200, {"ok": True})
                return

            if path == f"{SECRET_SUB_PATH}/api/node":
                action = (data.get("action") or "").strip()
                if action == "add":
                    node_type = (data.get("type") or "").strip().lower()
                    if node_type not in NODE_TYPE_LABELS:
                        node_type = "proxy"
                    url = (data.get("url") or "").strip().rstrip("/")
                    name = (data.get("name") or data.get("domain") or "").strip()
                    if not url and name:
                        url = f"https://{name}"
                    elif url and not url.startswith(("http://", "https://")):
                        if name and not url.startswith(name):
                            url = f"https://{name}/{url.lstrip('/')}"
                        else:
                            url = "https://" + url
                    if not name:
                        name = extract_domain_from_url(url)
                    if not name or not url.startswith(("http://", "https://")):
                        self._send_json(400, {"ok": False, "error": "укажите корректный URL или домен ноды"})
                        return
                    if any(node["name"].casefold() == name.casefold() for node in NODES):
                        self._send_json(400, {"ok": False, "error": f"нода с доменом {name} уже существует"})
                        return
                    NODES.append({
                        "id": uuid.uuid4().hex,
                        "type": node_type,
                        "name": name,
                        "url": url,
                        "clients": [],
                        "supports_json": bool(data.get("supports_json", True)),
                    })
                elif action == "delete":
                    node_id = (data.get("node") or "").strip()
                    node = next((item for item in NODES if item["id"] == node_id), None)
                    if not node:
                        self._send_json(400, {"ok": False, "error": "нода не найдена"})
                        return
                    if node.get("clients", []):
                        self._send_json(400, {"ok": False, "error": "сначала удалите клиентов этой ноды"})
                        return
                    NODES.remove(node)
                elif action == "edit":
                    node_id = (data.get("node") or "").strip()
                    node = next((item for item in NODES if item["id"] == node_id), None)
                    if not node:
                        self._send_json(400, {"ok": False, "error": "нода не найдена"})
                        return
                    node_type = (data.get("type") or "").strip().lower()
                    if node_type in NODE_TYPE_LABELS:
                        node["type"] = node_type
                    name = (data.get("name") or data.get("domain") or "").strip()
                    url = (data.get("url") or "").strip().rstrip("/")
                    if not name:
                        name = node["name"]
                    if not url:
                        url = node["url"]
                    elif not url.startswith(("http://", "https://")):
                        if name and not url.startswith(name):
                            url = f"https://{name}/{url.lstrip('/')}"
                        else:
                            url = "https://" + url
                    if not name:
                        self._send_json(400, {"ok": False, "error": "укажите домен (имя) ноды"})
                        return
                    if not url.startswith(("http://", "https://")):
                        self._send_json(400, {"ok": False, "error": "укажите URL ноды (например: node.example.com/subs)"})
                        return
                    if name != node["name"] and any(
                        item["name"].casefold() == name.casefold() and item["id"] != node_id for item in NODES
                    ):
                        self._send_json(400, {"ok": False, "error": "нода с таким доменом/именем уже существует"})
                        return
                    node["name"] = name
                    node["url"] = url
                    if "supports_json" in data:
                        node["supports_json"] = bool(data["supports_json"])
                else:
                    self._send_json(400, {"ok": False, "error": "неизвестное действие"})
                    return
                try:
                    save_nodes()
                except OSError as exc:
                    self._send_json(500, {"ok": False, "error": f"не удалось сохранить ноды: {exc}"})
                    return
                self._send_json(200, {"ok": True})
                return

            client = (data.get("client") or "").strip()
            value = (data.get("value") or "").strip()
            if client not in all_clients() and client not in FORCE_SUBS:
                self._send_json(400, {"ok": False, "error": f"неизвестный клиент: {client}"})
                return
            if value:
                if not value.startswith("vless://"):
                    self._send_json(400, {"ok": False, "error": "ссылка должна начинаться с vless://"})
                    return
                new_force = dict(FORCE_SUBS)
                new_force[client] = encode_override_value(value)
                action = "set"
            else:
                new_force = dict(FORCE_SUBS)
                new_force.pop(client, None)
                action = "cleared"
            try:
                save_force_subs(new_force)
            except Exception as e:
                log.error("failed to save %s: %r", FORCE_FILE, e)
                self._send_json(500, {"ok": False, "error": f"не удалось сохранить оверрайд: {e}"})
                return
            FORCE_SUBS = new_force
            log.info("override %s for client %s", action, client)
            self._send_json(200, {"ok": True})

    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _wants_html(self):
        params = self._query_params()
        if "html" in params or "raw" in params:
            return "html" in params
        return "text/html" in self.headers.get("Accept", "")

    def _public_base(self):
        if PUBLIC_URL:
            return PUBLIC_URL
        scheme = self.headers.get("X-Forwarded-Proto", "https").split(",")[0].strip().lower()
        if scheme not in ("http", "https"):
            scheme = "https"
        host = (self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "").strip()
        return f"{scheme}://{host}".rstrip("/") if host else None

    def _node_cards(self):
        esc = html.escape
        cards = []
        for node in NODES:
            group = node["id"]
            url = node["url"]
            if not url:
                continue
            node_type = get_node_type(node)
            type_label = get_node_type_label(node)
            p = [f'<div class="card" data-search="{esc(node["name"])} {esc(type_label)}">']
            p.append(
                f'<div class="client-header">'
                f'<span class="client-name-badge">'
                f'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>'
                f'<span>{esc(node["name"])}</span></span>'
                f'<span style="display:flex;gap:6px;align-items:center">'
                f'<span class="node-type-badge {node_type}">{esc(type_label)}</span>'
                f'<button type="button" class="btn-sm btn-node-edit" data-node="{esc(node["id"])}" title="Редактировать ноду" aria-label="Редактировать ноду">'
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg></button>'
                f'<button type="button" class="btn-sm btn-node-delete" data-node="{esc(node["id"])}" title="Удалить ноду" aria-label="Удалить ноду">'
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14H6L5 6m3 0V4h8v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg></button></span></div>'
            )
            p.append('<div class="client-link-group">')
            p.append(
                '<div class="client-link-label">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>'
                '<span>Подписочная ссылка ноды</span></div>'
            )
            p.append(
                f'<div class="client-link-row">'
                f'<span class="client-link-text" title="{esc(url)}">{esc(url)}</span>'
                f'<button type="button" class="btn-sm btn-copy" data-url="{esc(url)}">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
                '<span>Копировать</span></button>'
                f'</div>'
            )
            p.append('</div></div>')
            cards.append("\n".join(p))
        return cards

    def _client_sections(self):
        base = self._public_base()
        if not base:
            log.warning("no public base URL (PUBLIC_URL not set, Host header missing); using relative links")
            base = ""
        sections = []
        seen = set()
        idx = 0
        for node in NODES:
            clients = node.get("clients", [])
            if not clients:
                continue
            cards = []
            for client in clients:
                if client in seen:
                    continue
                cards.append(self._card_html(client, node, base, idx))
                seen.add(client)
                idx += 1
            if cards:
                type_label = get_node_type_label(node)
                sec_title = f'Клиенты · [{type_label}] {html.escape(node["name"])}'
                sections.append(self._section_html(sec_title, "\n".join(cards), f'node-{html.escape(node["id"])}'))
        force_clients = [c for c in sorted(FORCE_SUBS) if c not in seen]
        if force_clients:
            cards = []
            for client in force_clients:
                cards.append(self._card_html(client, None, base, idx))
                idx += 1
            sections.append(self._section_html("Клиенты · Кастом (force-subs.yml)", "\n".join(cards), "force-subs"))
        return "\n".join(sections)

    def _section_html(self, title, cards, section_id=None):
        sid_attr = f' data-section="{html.escape(section_id)}"' if section_id else ''
        return (
            f'<div class="section-header" role="button" tabindex="0"{sid_attr}>'
            f'<span class="chevron"><svg width="10" height="6" viewBox="0 0 10 6" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M1 1L5 5L9 1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></span>'
            f'<span class="section-title-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg></span>'
            f'<span>{title}</span><span class="line"></span></div>'
            f'<div class="cards-grid stacked"{sid_attr}>\n{cards}\n    </div>'
        )

    def _card_html(self, client, node, base, idx):
        esc = html.escape
        force = client in FORCE_SUBS
        sub_url = f"{base}/{SECRET_SUB_PATH}/{client}" if base else f"/{SECRET_SUB_PATH}/{client}"
        direct_url = f'{node["url"]}/{client}' if node else None

        force_tag = (
            '<span class="force-tag">'
            '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>'
            '<span>override</span></span>'
        ) if force else ""
        qr_panel_id = f"qr-panel-{idx}"

        node_type = get_node_type(node) if node else "force"
        type_label = get_node_type_label(node) if node else GROUP_LABELS["force"]
        search_text = f'{client} {node["name"]} {type_label}' if node else client
        p = [f'<div class="card" data-search="{esc(search_text)}">']
        p.append(
            f'<div class="client-header">'
            f'<span class="client-name-badge">'
            f'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>'
            f'<span>{esc(client)}</span></span>'
            f'<span style="display:flex;gap:6px;align-items:center">'
            + (f'<span class="node-type-badge {node_type}">{esc(type_label)}</span>'
               f'<span class="group-badge">{esc(node["name"])}</span>' if node else f'<span class="group-badge">{GROUP_LABELS["force"]}</span>')
            + f'{force_tag}'
            + (f'<button type="button" class="btn-sm btn-client-edit" data-client="{esc(client)}" title="Редактировать клиента" aria-label="Редактировать клиента">'
               '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg></button>'
               + (f'<button type="button" class="btn-sm btn-client-delete" data-client="{esc(client)}" title="Удалить клиента" aria-label="Удалить клиента">'
               '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14H6L5 6m3 0V4h8v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg></button>' if node else '')
               + '</span></div>')
        )
        p.append('<div class="client-link-grid">')

        p.append('<div class="client-link-col">')
        p.append(
            '<div class="client-link-label">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"/></svg>'
            '<span>Через Сервер подписок</span></div>'
        )
        p.append(
            f'<div class="client-link-row">'
            f'<span class="client-link-text" title="{esc(sub_url)}">{esc(sub_url)}</span>'
            f'<button type="button" class="btn-sm btn-copy" data-url="{esc(sub_url)}">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
            '<span>Копировать</span></button>'
            f'<button type="button" class="btn-sm btn-qr" data-target="#{qr_panel_id}">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>'
            '<span>QR</span></button>'
            f'</div>'
        )
        sub_json_url = f"{base}/{SECRET_SUB_PATH}/json/{client}" if base else f"/{SECRET_SUB_PATH}/json/{client}"
        p.append(
            '<div class="client-link-label">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>'
            '<span>Через Сервер подписок (JSON)</span></div>'
        )
        p.append(
            f'<div class="client-link-row">'
            f'<span class="client-link-text" title="{esc(sub_json_url)}">{esc(sub_json_url)}</span>'
            f'<button type="button" class="btn-sm btn-copy" data-url="{esc(sub_json_url)}">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
            '<span>Копировать</span></button>'
            f'<button type="button" class="btn-sm btn-qr" data-target="#{qr_panel_id}">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>'
            '<span>QR</span></button>'
            f'</div>'
        )
        p.append('</div>')

        p.append('<div class="client-link-col">')
        p.append(
            '<div class="client-link-label">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>'
            '<span>Прямая ссылка</span></div>'
        )
        if direct_url:
            direct_json_url = f"{node["url"]}/json/{client}"
            p.append(
                f'<div class="client-link-row">'
                f'<span class="client-link-text" title="{esc(direct_url)}">{esc(direct_url)}</span>'
                f'<button type="button" class="btn-sm btn-copy" data-url="{esc(direct_url)}">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
                '<span>Копировать</span></button>'
                f'<button type="button" class="btn-sm btn-qr" data-target="#{qr_panel_id}">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>'
                '<span>QR</span></button>'
                f'</div>'
            )
            p.append(
                '<div class="client-link-label">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>'
                '<span>Прямая ссылка (JSON)</span></div>'
            )
            p.append(
                f'<div class="client-link-row">'
                f'<span class="client-link-text" title="{esc(direct_json_url)}">{esc(direct_json_url)}</span>'
                f'<button type="button" class="btn-sm btn-copy" data-url="{esc(direct_json_url)}">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
                '<span>Копировать</span></button>'
                f'<button type="button" class="btn-sm btn-qr" data-target="#{qr_panel_id}">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>'
                '<span>QR</span></button>'
                f'</div>'
            )
        else:
            if not node:
                p.append('<div class="note">Кастомная подписка из force-subs.yml — прямого таргета нет.</div>')
            else:
                p.append('<div class="note">Таргет-URL для группы не настроен.</div>')
        p.append('</div>')

        p.append('</div>')

        qr_items = []
        qr_items.append(f'<div class="qr-item" data-qr-val="{esc(sub_url)}"><img src="" alt="QR"><span>Через Сервер</span></div>')
        if direct_url:
            qr_items.append(f'<div class="qr-item" data-qr-val="{esc(direct_url)}"><img src="" alt="QR"><span>Прямая ссылка</span></div>')
        
        supports_json = node.get("supports_json", True)
        if supports_json:
            qr_items.append(f'<div class="qr-item" data-qr-val="{esc(sub_json_url)}"><img src="" alt="QR"><span>Через Сервер (JSON)</span></div>')
            if direct_url:
                qr_items.append(f'<div class="qr-item" data-qr-val="{esc(direct_json_url)}"><img src="" alt="QR"><span>Прямая ссылка (JSON)</span></div>')
        p.append(f'<div class="qr-panel" id="{qr_panel_id}">' + "".join(qr_items) + '</div>')

        if supports_json:
            additional_json_nodes = [n for n in NODES if client in n.get("json_clients", [])]
            p.append('<div class="additional-nodes-section" style="margin-top: 15px; padding: 12px; background: rgba(59, 130, 246, 0.05); border: 1px solid rgba(59, 130, 246, 0.15); border-radius: 8px;">')
            p.append('<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 8px;">')
            p.append('<div style="font-size: 13px; font-weight: 600; color: #60a5fa; display:flex; align-items:center; gap:6px;">'
                     '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>'
                     'Дополнительные ноды (только JSON)</div>')
            p.append('<div class="info-tooltip-container">'
                     '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>'
                     f'<div class="info-tooltip">В JSON-подписку клиента объединяются конфигурации основной и всех дополнительных нод. Приложение клиента каждые 30 секунд проверяет их доступность (загружая тестовый URL через каждую ноду) и автоматически перенаправляет трафик через самую быструю рабочую ноду.</div>'
                     '</div>')
            p.append('</div>')
            if additional_json_nodes:
                for an in additional_json_nodes:
                    p.append(f'<div style="display:flex; justify-content: space-between; align-items:center; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255,255,255,0.1); padding: 6px 10px; border-radius: 6px; margin-bottom: 6px; font-size:13px;">')
                    p.append(f'<span>[{esc(get_node_type_label(an))}] {esc(an["name"])}</span>')
                    p.append(f'<button type="button" class="btn-sm btn-json-node-delete" data-client="{esc(client)}" data-node="{esc(an["id"])}" style="color:var(--danger-color); padding:4px; border:none; background:transparent; cursor:pointer;" title="Удалить"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14H6L5 6m3 0V4h8v2"></path></svg></button>')
                    p.append('</div>')

            available_nodes = [n for n in NODES if n != node and client not in n.get("json_clients", [])]
            if available_nodes:
                opts = "".join(f'<div class="node-select-option{" selected" if n["id"] == available_nodes[0]["id"] else ""}" data-value="{esc(n["id"])}">[{esc(get_node_type_label(n))}] {esc(n["name"])}</div>' for n in available_nodes)
                first_node = available_nodes[0]
                p.append(f'<div style="display:flex; gap: 8px; margin-top:8px; align-items:center;">')
                p.append(f'<button type="button" class="btn btn-sm btn-json-node-add" data-client="{esc(client)}" data-select="add-json-{qr_panel_id}" style="height: 32px; padding: 0 12px; font-size:13px; font-weight:500;">Добавить</button>')
                p.append(f'<div class="node-select" style="flex:1; min-width: 0;">'
                         f'<input type="hidden" id="add-json-{qr_panel_id}" value="{esc(first_node["id"])}">'
                         f'<button type="button" class="node-select-trigger" style="height: 32px; min-height: 32px; padding: 0 12px; margin: 0;"><span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">[{esc(get_node_type_label(first_node))}] {esc(first_node["name"])}</span>'
                         f'<span class="node-select-arrow"><svg width="10" height="6" viewBox="0 0 10 6" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M1 1L5 5L9 1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></span></button>'
                         f'<div class="node-select-options">{opts}</div>'
                         f'</div>')
                p.append('</div>')
            else:
                p.append('<div style="font-size:12px; color:var(--text-muted); margin-top:8px; text-align:center;">Нет доступных нод для добавления</div>')
            p.append('</div>')

        override_raw = FORCE_SUBS.get(client)
        override_val = decode_override_value(override_raw) if override_raw else None
        p.append('<div class="override-block">')
        p.append(
            '<div class="client-link-label">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>'
            '<span>Кастомная подписка (override)</span></div>'
        )
        if override_val:
            p.append(
                f'<div class="override-row">'
                f'<span class="override-text" data-custom="{esc(override_val)}" title="{esc(override_val)}">{esc(override_val)}</span>'
                f'<button type="button" class="btn-sm btn-override" data-client="{esc(client)}">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>'
                '<span>Установить</span></button>'
                f'<button type="button" class="btn-sm btn-override-clear" data-client="{esc(client)}">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>'
                '<span>Очистить</span></button>'
                f'</div>'
            )
        else:
            p.append(
                f'<div class="override-row">'
                f'<span class="override-text muted" data-custom="__none__">нет кастомной подписки</span>'
                f'<button type="button" class="btn-sm btn-override" data-client="{esc(client)}">'
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>'
                '<span>Установить</span></button>'
                f'</div>'
            )
        p.append(
            '<div class="override-editor">'
            '<textarea class="override-input" rows="3" placeholder="Вставьте сюда ссылку подписки vless://..."></textarea>'
            f'<div class="override-hint">Подключение к /{esc(SECRET_SUB_PATH)}/{esc(client)} будет отдавать указанную ссылку.</div>'
            '<div class="override-editor-actions">'
            f'<button type="button" class="btn-sm btn-override-save" data-client="{esc(client)}">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>'
            '<span>Сохранить</span></button>'
            '<button type="button" class="btn-sm btn-override-cancel">Отмена</button>'
            '</div></div>'
        )
        p.append('</div>')

        p.append(self._client_status_html(client))
        p.append('</div>')
        return "\n".join(p)

    def _client_status_html(self, client):
        esc = html.escape
        with ACTIVITY_LOCK:
            activity = CLIENT_ACTIVITY.get(client)
        state = get_client_sync_state(client)
        if state == "never" or not activity:
            return (
                f'<div class="client-status" data-client="{esc(client)}" data-time="" data-timestamp="0">'
                '<span class="status-dot st-never"></span>'
                '<span class="status-text">Синхронизации не было</span>'
                '</div>'
            )
        status = activity.get("status")
        dot_class = f"st-{state}"
        if isinstance(status, int) and not (200 <= status < 300):
            dot_class = "st-err"
        if activity.get("node_name"):
            src = f'через «{activity["node_name"]}»'
        elif activity.get("source") == "force":
            src = "через кастом"
        else:
            src = ""
        time_str = activity.get("time") or "—"
        ts_val = activity.get("timestamp") or 0
        text = (
            f'Последняя синхронизация: {time_str}'
            + (f' · HTTP {status}' if status else '')
            + (f' · {activity["bytes"]} B' if activity.get("bytes") else "")
            + (f' · {src}' if src else "")
        )
        return (
            f'<div class="client-status" data-client="{esc(client)}" data-time="{esc(time_str)}" data-timestamp="{ts_val}">'
            f'<span class="status-dot {dot_class}"></span>'
            f'<span class="status-text" title="{esc(text)}">{esc(text)}</span>'
            '</div>'
        )

    def _list_html(self):
        sections = self._client_sections() or '<div class="note">Клиенты не настроены.</div>'
        nodes = "\n".join(self._node_cards()) or '<div class="note">Подписочные URL нод не настроены.</div>'
        all_c = list(all_clients()) + [c for c in FORCE_SUBS if c not in all_clients()]
        total = len(all_c)
        count_recent = sum(1 for c in all_c if get_client_sync_state(c) == "recent")
        count_ever = sum(1 for c in all_c if get_client_sync_state(c) == "ever")
        count_never = sum(1 for c in all_c if get_client_sync_state(c) == "never")
        options = "".join(
            f'<div class="node-select-option" data-value="{html.escape(node["id"], quote=True)}">[{html.escape(get_node_type_label(node))}] {html.escape(node["name"])}</div>'
            for node in NODES
        )
        first_node = NODES[0] if NODES else None
        first_label = f'[{get_node_type_label(first_node)}] {first_node["name"]}' if first_node else "Нет доступных нод"
        node_picker = (
            f'<div class="node-select" id="node-select">'
            f'<input type="hidden" id="client-node" value="{html.escape(first_node["id"], quote=True) if first_node else ""}">'
            f'<button type="button" class="node-select-trigger"><span id="client-node-label">{html.escape(first_label)}</span>'
            '<span class="node-select-arrow"><svg width="10" height="6" viewBox="0 0 10 6" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M1 1L5 5L9 1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></span></button>'
            f'<div class="node-select-options">{options}</div></div>'
        )
        management = (
            '<div class="management-grid">'
            '<div class="management-panel">'
            '<div class="management-title">'
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg>'
            '<span>Добавить клиента</span></div>'
            f'<form class="management-row" id="add-client-form">{node_picker}<input id="new-client" placeholder="Имя нового клиента" required>'
            '<button class="btn-sm btn-primary" type="submit">'
            '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>'
            '<span>Добавить</span></button></form>'
            '<div id="add-client-json-nodes" style="display:flex; flex-wrap:wrap; gap:12px; margin-top:10px;"></div>'
            '</div>'
            '<div class="management-panel node-management">'
            '<div class="management-title">'
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>'
            '<span>Добавить ноду</span></div>'
            '<form id="add-node-form">'
            '<div class="management-row">'
            '<div class="node-select" id="new-node-type-select" style="min-width: 120px; flex: 0 0 120px;">'
            '<input type="hidden" id="new-node-type" value="proxy">'
            '<button type="button" class="node-select-trigger"><span>Proxy</span>'
            '<span class="node-select-arrow"><svg width="10" height="6" viewBox="0 0 10 6" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M1 1L5 5L9 1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></span></button>'
            '<div class="node-select-options">'
            '<div class="node-select-option selected" data-value="proxy">Proxy</div>'
            '<div class="node-select-option" data-value="freedom">Freedom</div>'
            '</div></div>'
            '<input id="new-node-url" placeholder="https://node.example.com/subs" required>'
            '<button class="btn-sm btn-primary" type="submit">'
            '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>'
            '<span>Добавить</span></button></div>'
            '<label class="custom-checkbox-wrapper" style="font-size:12px; margin-top:10px;">'
            '<input type="checkbox" id="new-node-json" checked>'
            '<span>Поддерживает JSON подписки</span>'
            '</label></form>'
            '<div id="management-message" class="management-error" hidden></div></div></div>'
        )
        body = (
            PAGE_TEMPLATE.replace("__SECTIONS__", sections)
            .replace("__NODES__", nodes)
            .replace("__MANAGEMENT__", management)
            .replace("__SEARCH__", '<input id="client-search" class="header-search" placeholder="поиск" aria-label="поиск">')
            .replace("__COUNT_TOTAL__", str(total))
            .replace("__COUNT_RECENT__", str(count_recent))
            .replace("__COUNT_EVER__", str(count_ever))
            .replace("__COUNT_NEVER__", str(count_never))
            .replace("__RAW_URL__", f"/{SECRET_SUB_PATH}?raw=1")
            .replace("__AUTH_ACTIONS__", f'<a class="btn-logout" href="/{SECRET_SUB_PATH}/logout">Выйти</a>' if ADMIN_USER and ADMIN_PASSWORD else "")
            .replace("__API_OVERRIDE__", f"/{SECRET_SUB_PATH}/api/override")
            .replace("__API_CLIENT__", f"/{SECRET_SUB_PATH}/api/client")
            .replace("__API_NODE__", f"/{SECRET_SUB_PATH}/api/node")
            .replace("__API_RESET__", f"/{SECRET_SUB_PATH}/api/reset")
            .replace("__LOGS_URL__", f"/{SECRET_SUB_PATH}/api/logs")
            .replace("__NODES_JSON__", json.dumps(NODES, ensure_ascii=False).replace("</", "<\\/"))
            .encode("utf-8")
        )
        log.info("200 html interface (%d cards)", total)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _log_tail(self):
        """Return (recent log lines, file inode, byte size) for the SSE backlog."""
        try:
            size = os.path.getsize(LOG_FILE)
        except OSError:
            return b"", None, 0
        start = max(0, size - LOG_HISTORY_BYTES)
        if start:
            with open(LOG_FILE, "rb") as f:
                f.seek(start)
                data = f.read()
            first_nl = data.find(b"\n")
            if first_nl != -1:
                data = data[first_nl + 1:]
        else:
            with open(LOG_FILE, "rb") as f:
                data = f.read()
        lines = data.splitlines()
        tail = b"\n".join(lines[-LOG_HISTORY_LINES:])
        try:
            st = os.stat(LOG_FILE)
            inode, size = st.st_ino, st.st_size
        except OSError:
            inode, size = None, 0
        return tail, inode, size

    def _log_file_info(self):
        try:
            st = os.stat(LOG_FILE)
            return st.st_ino, st.st_size
        except OSError:
            return None, 0

    def _emit_log_events(self, raw):
        if not raw:
            return
        text = raw.decode("utf-8", errors="replace")
        for line in text.splitlines():
            line = line.rstrip()
            if not line:
                continue
            match = LOG_LINE_RE.match(line)
            if match:
                ts, level, msg = match.group(1), match.group(2), match.group(3)
            else:
                ts, level, msg = "", "INFO", line
            payload = json.dumps({"time": ts, "level": level, "message": msg}, ensure_ascii=False)
            self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _stream_logs(self):
        """Server-Sent Events stream tailing LOG_FILE (equivalent of docker logs -f).

        Emits ``message`` events for log lines and ``activity`` events for
        per-client subscription activity (drives the card status rows).
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        stream_queue = queue.Queue()
        with ACTIVITY_LOCK:
            ACTIVITY_SUBSCRIBERS.add(stream_queue)
        try:
            with ACTIVITY_LOCK:
                snapshot = [json.dumps(a, ensure_ascii=False) for a in CLIENT_ACTIVITY.values()]
            for payload in snapshot:
                self.wfile.write(f"event: activity\ndata: {payload}\n\n".encode("utf-8"))

            tail, last_inode, pos = self._log_tail()
            self._emit_log_events(tail)
            last_active = time.time()
            last_reset = LOG_RESET_EVENT
            while True:
                while True:
                    try:
                        payload = stream_queue.get_nowait()
                    except queue.Empty:
                        break
                    self.wfile.write(f"event: activity\ndata: {payload}\n\n".encode("utf-8"))
                inode, size = self._log_file_info()
                if LOG_RESET_EVENT != last_reset:
                    last_reset = LOG_RESET_EVENT
                    last_inode = inode
                    pos = 0
                    last_active = time.time()
                if inode != last_inode:
                    last_inode = inode
                    pos = 0
                if size > pos:
                    with open(LOG_FILE, "rb") as f:
                        f.seek(pos)
                        chunk = f.read(size - pos)
                    pos = size
                    self._emit_log_events(chunk)
                    last_active = time.time()
                elif time.time() - last_active > 15:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    last_active = time.time()
                time.sleep(0.7)
        except (BrokenPipeError, ConnectionResetError, OSError):
            log.info("log stream closed by client")
        finally:
            with ACTIVITY_LOCK:
                ACTIVITY_SUBSCRIBERS.discard(stream_queue)

    def _list_subscriptions(self):
        blocks = []
        total_urls = 0
        for node in NODES:
            clients = node.get("clients", [])
            url = (node.get("url") or "").rstrip("/")
            if not clients or not url:
                continue
            clients_line = ",".join(clients)
            url_lines = [f"{url}/{client}" for client in clients]
            total_urls += len(url_lines)
            blocks.append("\n".join([clients_line] + url_lines))
        separator = "========================"
        body = (f"\n{separator}\n".join(blocks) + "\n").encode("utf-8") if blocks else b""
        log.info("200 subscription list (%d urls across %d nodes)", total_urls, len(blocks))
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        log.info("request: %s", format % args)


def main():
    global FORCE_SUBS, NODES
    setup_file_logging()
    load_past_activity_from_logs(LOG_FILE)
    FORCE_SUBS = load_force_subs(FORCE_FILE)
    legacy_subs = None
    if nodes_file_is_empty(NODES_FILE):
        legacy_subs = load_subs(DATABASE_FILE)
        if not os.path.exists(DATABASE_FILE):
            log.info("no %s found, seeding node registry from environment", DATABASE_FILE)
    NODES = load_nodes(NODES_FILE, legacy_subs)
    if nodes_file_is_empty(NODES_FILE):
        try:
            save_nodes()
            log.info("initialized node registry %s (nodes.json is the source of truth)", NODES_FILE)
        except OSError as exc:
            log.warning("could not persist initial node configuration: %s", exc)
    log.info("listening on %s:%s, path prefix /%s, registry %s", HOST, PORT, SECRET_SUB_PATH, NODES_FILE)
    if ADMIN_USER and ADMIN_PASSWORD:
        log.info("admin auth enabled (user: %s)", ADMIN_USER)
    else:
        log.warning("admin auth DISABLED (set ADMIN_USER / ADMIN_PASSWORD)")
    log.info("RUSSIAN_SUB_URL=%s", RUSSIAN_SUB_URL or "(not set)")
    log.info("FOREIGN_SUB_URL=%s", FOREIGN_SUB_URL or "(not set)")
    log.info("PUBLIC_URL=%s", PUBLIC_URL or "(not set, derived from request headers)")
    log.info("nodes: %s", ", ".join(node["name"] for node in NODES) or "(none)")
    log.info("force overrides: %s", ", ".join(FORCE_SUBS) or "(none)")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
