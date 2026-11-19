"""나라장터(조달청) 공사 입찰공고 중 기술형입찰(턴키·대안·기술제안 등)만 받아 data/g2b.json 으로 저장.
인증키는 환경변수 G2B_API_KEY(GitHub 비밀값)에서만 읽고, 어디에도 출력하지 않는다.
재시험 시각: 2026-11-19 18:07 KST"""
import json, os, re, sys, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
KEY = os.environ.get("G2B_API_KEY", "").strip()
DAYS = int(os.environ.get("G2B_DAYS", "14"))
OUT = "data/g2b.json"
ENDPOINTS = [
    "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoCnstwk",
    "https://apis.data.go.kr/1230000/BidPublicInfoService05/getBidPblancListInfoCnstwk",
    "https://apis.data.go.kr/1230000/BidPublicInfoService04/getBidPblancListInfoCnstwk",
]
TECH = re.compile(r"턴키|일괄입찰|설계\s*[·ㆍ\.]?\s*시공|대안입찰|기술제안|실시설계\s*기술제안|기본설계\s*기술제안")
FIELDS = ["bidNtceNo", "bidNtceOrd", "bidNtceNm", "ntceInsttNm", "dminsttNm", "bidNtceDt", "bidClseDt", "opengDt",
          "pqApplDocRcptDt", "pqEvlRsltPblctDt", "presmptPrce", "asignBdgtAmt", "cntrctCnclsMthdNm", "bidMethdNm",
          "sucsfbidMthdNm", "ntceKindNm", "bidNtceDtlUrl", "bidNtceUrl", "cnstrtsiteRgnNm", "mainCnsttyNm"]

KEY_MODE = {"m": "encode"}

def call(url, params):
    q = urllib.parse.urlencode(params)
    if KEY_MODE["m"] == "encode":
        q += "&serviceKey=" + urllib.parse.quote(KEY, safe="")
    else:  # 이미 인코딩된 키(Encoding 키)를 그대로 사용
        q += "&serviceKey=" + KEY
    req = urllib.request.Request(url + "?" + q, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        m = re.search(r"<(?:returnAuthMsg|errMsg|resultMsg|returnReasonCode)>([^<]+)<", body)
        raise RuntimeError(f"HTTP {e.code}: " + (m.group(1) if m else re.sub(r"\s+", " ", body)[:160]))

def main():
    now = datetime.now(KST)
    meta = {"fetchedAt": now.strftime("%Y-%m-%dT%H:%M"), "ok": False, "days": DAYS, "endpoint": None, "total": 0, "matched": 0, "error": None}
    items_out = []
    if not KEY:
        meta["error"] = "G2B_API_KEY 비밀값이 비어 있거나 이 작업에 전달되지 않았습니다."
    else:
        bgn = (now - timedelta(days=DAYS)).strftime("%Y%m%d0000"); end = now.strftime("%Y%m%d2359")
        last_err = None
        errors = []
        meta["keyLooksEncoded"] = "%" in KEY
        attempts = [(ep, m) for m in (["raw", "encode"] if "%" in KEY else ["encode", "raw"]) for ep in ENDPOINTS]
        for ep, mode in attempts:
            KEY_MODE["m"] = mode
            try:
                rows, page = [], 1
                while True:
                    st, body = call(ep, {"pageNo": page, "numOfRows": 999, "inqryDiv": 1, "inqryBgnDt": bgn, "inqryEndDt": end, "type": "json"})
                    if body.lstrip().startswith("<"):
                        m = re.search(r"<(?:returnAuthMsg|errMsg|resultMsg)>([^<]+)<", body)
                        raise RuntimeError("XML 응답: " + (m.group(1) if m else body[:120]))
                    data = json.loads(body)
                    hdr = data.get("response", {}).get("header", {})
                    if str(hdr.get("resultCode", "00")) not in ("00", "0"):
                        raise RuntimeError(f"resultCode {hdr.get('resultCode')}: {hdr.get('resultMsg')}")
                    b = data.get("response", {}).get("body", {})
                    it = b.get("items") or []
                    if isinstance(it, dict): it = it.get("item", [])
                    if isinstance(it, dict): it = [it]
                    rows += it
                    total = int(b.get("totalCount") or 0)
                    if page * 999 >= total or not it or page >= 20: break
                    page += 1
                meta["endpoint"] = ep.split("/1230000/")[1]
                meta["keyMode"] = mode
                meta["total"] = len(rows)
                for r in rows:
                    blob = " ".join(str(r.get(k, "")) for k in ("cntrctCnclsMthdNm", "bidMethdNm", "sucsfbidMthdNm", "bidNtceNm", "ntceKindNm"))
                    if TECH.search(blob):
                        items_out.append({k: r.get(k, "") for k in FIELDS if r.get(k, "") not in (None, "")})
                meta["ok"] = True
                last_err = None
                break
            except Exception as e:  # noqa
                last_err = f"{ep.split('/1230000/')[1]} [{mode}]: {str(e)[:200]}"
                errors.append(last_err)
                continue
        if last_err:
            meta["error"] = last_err
            meta["errors"] = errors
    seen, uniq = set(), []
    for x in sorted(items_out, key=lambda x: (x.get("bidNtceDt", ""), x.get("bidNtceOrd", "")), reverse=True):
        k = x.get("bidNtceNo")
        if k in seen: continue
        seen.add(k); uniq.append(x)
    meta["matched"] = len(uniq)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps({"meta": meta, "items": uniq}, ensure_ascii=False, indent=0))
    print(json.dumps(meta, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
