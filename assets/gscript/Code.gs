// NetBridge Google Script relay (original code, MIT). Deploy it in YOUR OWN Google account:
//   script.google.com -> New project -> paste this -> change AUTH_KEY -> Deploy -> New deployment -> Web app
//   Execute as: Me   |   Who has access: Anyone   -> copy the "/exec" URL into NetBridge.
const AUTH_KEY = '__AUTH_KEY__';

function doPost(e) {
  try {
    const r = JSON.parse(e.postData.contents);
    if (r.k !== AUTH_KEY) return out({ e: 'auth' });
    if (!/^https?:\/\//i.test(r.u || '')) return out({ e: 'bad url' });
    const opt = { method: String(r.m || 'GET').toLowerCase(), headers: r.h || {},
                  muteHttpExceptions: true, followRedirects: false, validateHttpsCertificates: true };
    for (const k in opt.headers) {
      if (k.toLowerCase() === 'content-type') { opt.contentType = opt.headers[k]; delete opt.headers[k]; break; }
    }
    if (r.b) opt.payload = Utilities.base64Decode(r.b);
    const resp = UrlFetchApp.fetch(r.u, opt);
    return out({ s: resp.getResponseCode(), h: resp.getAllHeaders(), b: Utilities.base64Encode(resp.getContent()) });
  } catch (err) {
    return out({ e: String(err) });
  }
}

function doGet() { return ContentService.createTextOutput('NetBridge relay is running'); }

function out(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }
