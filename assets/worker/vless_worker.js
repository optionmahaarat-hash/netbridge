// NetBridge personal VLESS-over-WebSocket relay for Cloudflare Workers (original code, MIT).
// Deployed to YOUR OWN Cloudflare account. Optional "?proxyip=host[:port]" is used when a direct connection fails.
import { connect } from 'cloudflare:sockets';

const UUID = '__UUID__';

export default {
  async fetch(request) {
    if (request.headers.get('Upgrade') !== 'websocket') {
      return new Response('OK', { status: 200 });
    }
    const url = new URL(request.url);
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    server.accept();
    session(server, url.searchParams.get('proxyip'));
    return new Response(null, { status: 101, webSocket: client });
  },
};

function uuidBytes(s) {
  const h = s.replace(/-/g, '');
  const out = new Uint8Array(16);
  for (let i = 0; i < 16; i++) out[i] = parseInt(h.substr(i * 2, 2), 16);
  return out;
}
const WANT = uuidBytes(UUID);

function parseHeader(buf) {
  const v = new Uint8Array(buf);
  if (v.length < 24) return null;
  for (let i = 0; i < 16; i++) if (v[1 + i] !== WANT[i]) return null;
  let p = 17 + 1 + v[17];                       // version, uuid, addons length, addons
  const cmd = v[p++];                           // 1 = TCP
  if (cmd !== 1) return null;
  const port = (v[p] << 8) | v[p + 1]; p += 2;
  const atyp = v[p++];
  let host;
  if (atyp === 1) { host = Array.from(v.slice(p, p + 4)).join('.'); p += 4; }
  else if (atyp === 2) { const n = v[p++]; host = new TextDecoder().decode(v.slice(p, p + n)); p += n; }
  else if (atyp === 3) {
    const parts = [];
    for (let i = 0; i < 8; i++) parts.push(((v[p + i * 2] << 8) | v[p + i * 2 + 1]).toString(16));
    host = parts.join(':'); p += 16;
  } else return null;
  return { version: v[0], host, port, rest: v.slice(p) };
}

function session(ws, proxyip) {
  let writer = null;
  let socket = null;
  let first = true;
  let chain = Promise.resolve();                 // messages are handled strictly in order (open() is async)

  const close = () => { try { ws.close(); } catch (e) {} try { socket && socket.close(); } catch (e) {} };

  async function open(h, resp) {
    const tryConnect = async (host, port) => {
      const s = connect({ hostname: host, port });
      await s.opened;
      return s;
    };
    try { socket = await tryConnect(h.host, h.port); }
    catch (e) {
      if (!proxyip) throw e;
      const [ph, pp] = proxyip.split(':');
      socket = await tryConnect(ph, pp ? parseInt(pp, 10) : h.port);
    }
    writer = socket.writable.getWriter();
    if (h.rest.length) await writer.write(h.rest);
    let head = resp;
    socket.readable.pipeTo(new WritableStream({
      write(chunk) {
        if (head) { const m = new Uint8Array(head.length + chunk.length); m.set(head); m.set(chunk, head.length); head = null; ws.send(m); }
        else ws.send(chunk);
      },
      close() { close(); },
      abort() { close(); },
    })).catch(close);
  }

  ws.addEventListener('message', (ev) => { chain = chain.then(() => onMessage(ev)); });
  async function onMessage(ev) {
    try {
      const data = ev.data instanceof ArrayBuffer ? ev.data : await new Response(ev.data).arrayBuffer();
      if (first) {
        first = false;
        const h = parseHeader(data);
        if (!h) { close(); return; }
        await open(h, new Uint8Array([h.version, 0]));
      } else if (writer) {
        await writer.write(new Uint8Array(data));
      }
    } catch (e) { close(); }
  }
  ws.addEventListener('close', close);
  ws.addEventListener('error', close);
}
