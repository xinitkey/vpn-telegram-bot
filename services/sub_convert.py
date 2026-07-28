import base64
import json
import logging
import urllib.parse
from aiohttp import ClientSession, ClientTimeout

log = logging.getLogger(__name__)

CLASH_CONFIG_TEMPLATE = '''\
port: 7890
socks-port: 7891
allow-lan: true
mode: Rule
log-level: info
external-controller: :9090

proxies:
{proxies}
proxy-groups:
  - name: Proxy
    type: select
    proxies:
      - Auto
      - DIRECT
{group_proxies}
  - name: Auto
    type: url-test
    url: http://www.gstatic.com/generate_204
    interval: 300
    proxies:
{auto_proxies}
  - name: DIRECT
    type: select
    proxies:
      - DIRECT

rules:
  - MATCH,Proxy
'''


def _b64decode(data: bytes) -> str:
    try:
        return base64.b64decode(data).decode('utf-8', errors='replace')
    except Exception:
        return data.decode('utf-8', errors='replace')


async def fetch_sub(session: ClientSession, url: str) -> str:
    try:
        async with session.get(url, timeout=ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                log.warning("sub fetch %s: %s", resp.status, url[:60])
                return ''
            data = await resp.read()
            return _b64decode(data)
    except Exception as e:
        log.error("fetch fail %s: %s", url[:60], e)
        return ''


def parse_vless(url: str) -> dict:
    p = urllib.parse.urlparse(url)
    q = urllib.parse.parse_qs(p.query)
    frag = urllib.parse.unquote(p.fragment or '')[:32]
    proxy = {
        'name': frag or ('VLESS-' + (p.username or '')[:8]),
        'type': 'vless',
        'server': p.hostname or '',
        'port': p.port or 443,
        'uuid': p.username or '',
    }
    if q.get('encryption', ['none'])[0] != 'none':
        proxy['encrypt'] = True
    if q.get('flow'):
        proxy['flow'] = q['flow'][0]
    if q.get('sni'):
        proxy['sni'] = q['sni'][0]
    if q.get('fp'):
        proxy['client-fingerprint'] = q['fp'][0]
    if q.get('pbk'):
        proxy['reality-opts'] = {'public-key': q['pbk'][0]}
        if q.get('sid'):
            proxy['reality-opts']['short-id'] = q['sid'][0]
    if q.get('security', [''])[0] in ('tls', 'reality'):
        proxy['tls'] = True
    net = q.get('type', [''])[0]
    proxy['network'] = net or 'tcp'
    return proxy


def parse_vmess(url: str) -> dict:
    raw = url[len('vmess://'):]
    if '#' in raw:
        raw = raw.split('#')[0]
    try:
        pad = 4 - len(raw) % 4 if len(raw) % 4 else 0
        data = json.loads(base64.b64decode(raw + '=' * pad))
    except Exception:
        return None
    name = (data.get('ps') or 'VMess')[:32]
    proxy = {
        'name': name,
        'type': 'vmess',
        'server': data.get('add', ''),
        'port': int(data.get('port', 443)),
        'uuid': data.get('id', ''),
        'alterId': int(data.get('aid', 0)),
        'cipher': data.get('scy', 'auto') or 'auto',
    }
    if data.get('tls'):
        proxy['tls'] = True
    net = data.get('net', 'tcp')
    if net:
        proxy['network'] = net
    host, path = data.get('host', ''), data.get('path', '')
    if net == 'ws':
        opts = {}
        if path: opts['path'] = path
        if host: opts['headers'] = {'Host': host}
        if opts: proxy['ws-opts'] = opts
    elif net == 'grpc' and data.get('serviceName'):
        proxy['grpc-opts'] = {'grpc-service-name': data['serviceName']}
    return proxy


def parse_ss(url: str) -> dict:
    raw = url[len('ss://'):]
    frag = ''
    if '#' in raw:
        raw, frag = raw.split('#', 1)
    if '?' in raw:
        raw = raw.split('?', 1)[0]
    try:
        decoded = base64.b64decode(raw).decode('utf-8')
        userinfo, _, hostport = decoded.rpartition('@')
        if not hostport:
            return None
        method, _, password = userinfo.partition(':')
        if not password:
            password = method
            method = 'chacha20-ietf-poly1305'
        host = hostport
        port = 443
        if ']' in hostport:
            host = hostport[:hostport.rindex(']') + 1]
            rest = hostport[hostport.rindex(']') + 1:]
            if rest.startswith(':'):
                port = int(rest[1:])
        elif ':' in hostport:
            host, _, port_str = hostport.rpartition(':')
            port = int(port_str)
        name = urllib.parse.unquote(frag or '')[:32]
        return {
            'name': name or 'SS',
            'type': 'ss',
            'server': host,
            'port': port,
            'cipher': method,
            'password': password,
        }
    except Exception:
        pass
    try:
        p = urllib.parse.urlparse(url)
        if p.password:
            method, _, password = urllib.parse.unquote(p.password).partition(':')
            if not password:
                password = method
                method = 'chacha20-ietf-poly1305'
            return {
                'name': urllib.parse.unquote(p.fragment or 'SS')[:32],
                'type': 'ss',
                'server': p.hostname or '',
                'port': p.port or 443,
                'cipher': method,
                'password': password,
            }
    except Exception:
        pass
    return None


def parse_trojan(url: str) -> dict:
    p = urllib.parse.urlparse(url)
    q = urllib.parse.parse_qs(p.query)
    frag = urllib.parse.unquote(p.fragment or '')[:32]
    proxy = {
        'name': frag or 'Trojan',
        'type': 'trojan',
        'server': p.hostname or '',
        'port': p.port or 443,
        'password': p.username or '',
        'udp': True,
    }
    if q.get('sni'): proxy['sni'] = q['sni'][0]
    elif q.get('peer'): proxy['sni'] = q['peer'][0]
    if q.get('allowInsecure', ['0'])[0] in ('1', 'true'):
        proxy['skip-cert-verify'] = True
    if q.get('fp'): proxy['client-fingerprint'] = q['fp'][0]
    if q.get('alpn'): proxy['alpn'] = q['alpn'][0].split(',')
    if q.get('type', [''])[0]:
        proxy['network'] = q['type'][0]
    return proxy


def to_clash_yaml(proxies: list) -> str:
    seen = set()
    unique = []
    for p in proxies:
        key = f"{p.get('server','')}:{p.get('port','')}:{p.get('type','')}"
        if key not in seen:
            seen.add(key)
            unique.append(p)

    if not unique:
        return ''

    def pval(v):
        if isinstance(v, bool):
            return str(v).lower()
        if isinstance(v, int):
            return str(v)
        if isinstance(v, str):
            if any(c in v for c in '{}[]"\':,#'):
                return json.dumps(v, ensure_ascii=False)
            return v
        return str(v)

    lines = []
    for p in unique:
        lines.append(f'  - name: "{p.get("name", "Unknown")}"')
        lines.append(f'    type: {p["type"]}')
        lines.append(f'    server: {p["server"]}')
        lines.append(f'    port: {p["port"]}')
        if p['type'] == 'ss':
            lines.append(f'    cipher: {p.get("cipher", "chacha20-ietf-poly1305")}')
            lines.append(f'    password: "{p.get("password", "")}"')
        elif p['type'] == 'vless':
            lines.append(f'    uuid: {p["uuid"]}')
            if not p.get('encrypt'):
                lines.append('    encrypt: false')
            if p.get('flow'):
                lines.append(f'    flow: {p["flow"]}')
            if p.get('tls'):
                lines.append('    tls: true')
            if p.get('sni'):
                lines.append(f'    sni: {p["sni"]}')
            if p.get('client-fingerprint'):
                lines.append(f'    client-fingerprint: {p["client-fingerprint"]}')
            if p.get('reality-opts'):
                lines.append('    reality-opts:')
                lines.append(f'      public-key: {p["reality-opts"]["public-key"]}')
                if p['reality-opts'].get('short-id'):
                    lines.append(f'      short-id: {p["reality-opts"]["short-id"]}')
            lines.append(f'    network: {p.get("network", "tcp")}')
            if p.get('network') == 'ws':
                lines.append('    ws-opts:')
                lines.append(f'      path: {p.get("ws-opts", {}).get("path", "/")}')
                lines.append('      headers:')
                lines.append(f'        Host: {p.get("ws-opts", {}).get("headers", {}).get("Host", p.get("sni", p["server"]))}')
        elif p['type'] == 'trojan':
            lines.append(f'    password: "{p.get("password", "")}"')
            lines.append('    udp: true')
            if p.get('sni'):
                lines.append(f'    sni: {p["sni"]}')
            if p.get('skip-cert-verify'):
                lines.append('    skip-cert-verify: true')
            if p.get('network'):
                lines.append(f'    network: {p["network"]}')
        elif p['type'] == 'vmess':
            lines.append(f'    uuid: {p["uuid"]}')
            lines.append(f'    alterId: {p.get("alterId", 0)}')
            lines.append(f'    cipher: {p.get("cipher", "auto")}')
            if p.get('tls'):
                lines.append('    tls: true')
            if p.get('network') and p['network'] != 'tcp':
                lines.append(f'    network: {p["network"]}')
            if p.get('ws-opts'):
                ws = p['ws-opts']
                lines.append('    ws-opts:')
                lines.append(f'      path: "{ws.get("path", "/")}"')
                if ws.get('headers'):
                    lines.append('      headers:')
                    lines.append(f'        Host: {ws["headers"].get("Host", "")}')
            if p.get('grpc-opts'):
                lines.append('    grpc-opts:')
                lines.append(f'      grpc-service-name: {p["grpc-opts"]["grpc-service-name"]}')

    proxies_yaml = '\n'.join(lines).rstrip()
    names = [p.get('name', 'Unknown') for p in unique]
    group_yaml = '\n'.join(f'      - "{n}"' for n in names)
    auto_yaml = '\n'.join(f'      - "{n}"' for n in names)

    return CLASH_CONFIG_TEMPLATE.format(
        proxies=proxies_yaml,
        group_proxies=group_yaml,
        auto_proxies=auto_yaml,
    )


async def convert(session: ClientSession, sub_url: str) -> str:
    text = await fetch_sub(session, sub_url)
    if not text:
        return ''

    lines = text.strip().splitlines()
    proxies = []
    for link in lines:
        link = link.strip()
        if not link or link.startswith('#'):
            continue
        try:
            if link.startswith('vless://'):
                p = parse_vless(link)
            elif link.startswith('vmess://'):
                p = parse_vmess(link)
            elif link.startswith('ss://'):
                p = parse_ss(link)
            elif link.startswith('trojan://'):
                p = parse_trojan(link)
            else:
                continue
            if p:
                proxies.append(p)
        except Exception as e:
            log.debug("parse fail %s: %s", link[:40], e)
            continue

    if not proxies:
        return ''

    return to_clash_yaml(proxies)
