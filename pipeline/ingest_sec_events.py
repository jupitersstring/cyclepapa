"""SEC filings that betray a coming catalyst, from EDGAR full-text search.

  proxy   a proxy contest: a dissident's materials (DFAN14A, PREN14A, DEFN14A,
          PRRN14A) or the company's contested proxy (PREC14A, DEFC14A)
  spin    a Form 10 registration (10-12B / 10-12G and amendments): a new
          company being registered, usually a spin-off. The parent is read
          from the information statement — its letter to the parent's holders
          ("Dear Honeywell Shareowner:") and the distribution ("Corteva will
          distribute all of the shares") — and its legal name and ticker from
          the document's own definition ("Resideo Technologies, Inc.
          ("Resideo")"); a unit that then merges into a buyer (a Reverse Morris
          Trust) names the buyer too. A registrant that distributes nothing is
          a private fund, an uplisting or a holding-company formation, and is
          labelled so
  tender  a third-party tender offer (SC TO-T), a going-private deal (SC
          13E3) or a target's response to one (SC 14D9)
  form3   an initial insider filing (Form 3): a new director, officer or 10%
          owner. Matched to the people monitor's tracked individuals, with the
          role read from the filing itself

Table sec_events: one row per filing (accession): kind, form, filed, the
company (subject) and the other party (dissident, bidder, parent, insider),
a detail field (spin parent + ticker, Form 3 role). Rolling windows: proxy and
tender 180 days, spin 365, form3 120. Idempotent: re-runs replace the window.
"""
import html, json, os, re, sqlite3, subprocess, sys, time
import datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")
UA = "cyclepapa-research admin@example.com"
FORMS = {
    "proxy": ["DFAN14A", "PREN14A", "DEFN14A", "PRRN14A", "PREC14A", "DEFC14A"],
    "spin": ["10-12B", "10-12G"],
    "tender": ["SC TO-T", "SC 13E3", "SC 14D9"],
    "form3": ["3"],
}
WINDOW = {"proxy": 180, "spin": 365, "tender": 180, "form3": 120}
_DN = re.compile(r"^(.*?)\s+(?:\(([A-Z0-9.,\- ]+)\)\s+)?\(CIK (\d+)\)\s*$")
_COMPANY = r"(?:Inc\.?|Incorporated|Corporation|Corp\.?|Company|plc|PLC|Holdings?|Ltd\.?|Limited|Group|N\.V\.|S\.A\.|AG|L\.P\.|LLC|Co\.)"

def curl(url, timeout=30):
    """b"" when EDGAR would not serve the page: its rate-limit page, or the 503
    "apology" page its archive server gives this shared address more often
    than not (the same request often succeeds seconds later)."""
    for attempt in range(6):
        out = subprocess.run(["curl", "-sk", "--compressed", "-m", str(timeout), "-A", UA, url],
                             capture_output=True).stdout
        head = out[:8000]
        if b"Rate Threshold Exceeded" in head or b"Undeclared Automated Tool" in head \
                or b"apology_objects" in head:
            time.sleep(1.5 + 2 * attempt)
            continue
        return out
    return b""

TICKERS_CACHE = os.path.join(os.path.dirname(DB), "sec_cache", "company_tickers.json")

def company_tickers():
    """SEC's CIK -> ticker list, kept on disk: when EDGAR won't serve it, the
    last good copy (tickers change slowly) rather than none."""
    body = curl("https://www.sec.gov/files/company_tickers.json")
    try:
        j = json.loads(body)
        os.makedirs(os.path.dirname(TICKERS_CACHE), exist_ok=True)
        with open(TICKERS_CACHE, "w") as f:
            json.dump(j, f)
        return j, "fresh"
    except ValueError:
        if os.path.exists(TICKERS_CACHE):
            return json.load(open(TICKERS_CACHE)), "cached copy"
    return None, "unavailable"

def search(form, start, end):
    """Every filing of `form` filed in [start, end]: {adsh: [hit sources]}.
    EDGAR's search caps a query at 10,000 hits: long windows are split."""
    days = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days
    if form == "3" and days > 10:                      # ~60 Form 3s a day
        out, s = {}, dt.date.fromisoformat(start)
        e_all = dt.date.fromisoformat(end)
        while s <= e_all:
            e = min(s + dt.timedelta(days=9), e_all)
            for k, v in search(form, s.isoformat(), e.isoformat()).items():
                out.setdefault(k, []).extend(v)
            s = e + dt.timedelta(days=1)
        return out
    out, frm = {}, 0
    q = form.replace(" ", "%20")
    while True:
        body = curl(f"https://efts.sec.gov/LATEST/search-index?q=%22%22&forms={q}&dateRange=custom"
                    f"&startdt={start}&enddt={end}&from={frm}")
        try:
            d = json.loads(body)
        except ValueError:
            return None                                # failed: not "no filings"
        hits = d.get("hits", {}).get("hits", [])
        for h in hits:
            src = h.get("_source", {})
            out.setdefault(src.get("adsh"), []).append(dict(src, _id=h.get("_id", "")))
        total = (d.get("hits", {}).get("total") or {}).get("value", 0)
        frm += len(hits)
        if not hits or frm >= total or frm >= 9900:
            break
        time.sleep(0.15)
    return out

def parties(src, tick_by_cik):
    """[(name, tickers, cik)] from a hit's display names."""
    out = []
    for dn in src.get("display_names") or []:
        m = _DN.match(dn.strip())
        if m:
            cik = str(int(m.group(3)))
            tks = [t.strip() for t in (m.group(2) or "").split(",") if t.strip()]
            if not tks and tick_by_cik.get(cik):
                tks = [tick_by_cik[cik]]
            out.append((m.group(1).strip(), tks, cik))
    return out

def text_of(cik, adsh, doc, limit=600000):
    """The document's text; None when EDGAR would not serve it (never read as
    a document that names nothing)."""
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/{doc}"
    raw = curl(url, timeout=60)[:limit].decode("utf-8", "ignore")
    if not raw.strip():
        return None
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw))

# How an information statement names the company handing out the shares: its
# letter to that company's holders ("Dear Honeywell Shareowner:", "Dear Resideo
# Technologies, Inc. ("Resideo") Stockholder:") and the distribution itself
# ("Honeywell currently plans to distribute all of the shares", "BD will
# distribute to its shareholders all of the issued and outstanding shares").
# A private fund registering under 12(g) ("a wholly owned subsidiary of FMR
# LLC") distributes nothing and names no parent.
_WORD = r"[A-Z][A-Za-z0-9&’'.\-]*"
_SHORT = rf"({_WORD}(?: (?:{_WORD}|&|and|of|de|du|la))*?)"
_SUFFIX_ONLY = r"(?:Inc\.?|Corp\.?|Corporation|Company|plc|PLC|Ltd\.?|Limited|N\.V\.|S\.A\.|AG|SE|AB|LLC)"
# ("MSG Sports will distribute to its stockholders shares of our Class A Common Stock")
_DIST = re.compile(_SHORT + rf"(?:,? {_SUFFIX_ONLY})?,? (?:currently )?(?:will|intends to|plans to|expects to|is expected to) "
                   r"distribute\b[^.]{0,160}?(?i:\bshares\b|\bstock\b|\bunits\b)")
_DEAR = re.compile(r"Dear (?:Fellow )?([^:\n]{2,90}?) (?:Stockholder|Shareholder|Shareowner|Unitholder|Holder)s?\s*:")
_NOT_PARENT = {"we", "us", "our", "spinco", "the company", "company", "fellow", "future", "valued", "current",
               "computershare", "the distribution agent", "distribution agent", "the transfer agent"}
_LEGAL = (rf"((?:{_WORD},? (?:(?:and|&|of|de|du|la) )?){{1,6}}"
          r"(?:Inc\.?|Incorporated|Corporation|Corp\.?|Company|plc|PLC|Holdings?|Ltd\.?|Limited|Group|N\.V\.|"
          r"S\.A\.|SE|AB|ASA|AG|L\.P\.|LLC|Co\.))")
_ACQ = re.compile(_SHORT + r" will acquire the [^.]{0,80}?(?:Business|business)")

def _resolve(short, text, idx, cidx):
    """(legal name, ticker) for a short name used in the document: its
    definition ("Resideo Technologies, Inc. ("Resideo")") when there is one,
    looked up in the listings index; else the short name itself."""
    from map_pb_tickers import norm
    m = re.search(_LEGAL + r"\s*\((?:the\s+)?[“\"]" + re.escape(short) + r"[”\"]", text)
    full = m.group(1).strip(" ,") if m else short
    while True:                          # "Dear Resideo Technologies, Inc." -> "Resideo Technologies, Inc."
        f2 = re.sub(r"^(?:Dear|The|And|Of|By|From|To|In|On|For|With|Between|Among|Following|Accordingly)\s+", "", full)
        if f2 == full:
            break
        full = f2
    # a definition must be of the same name ("a Delaware Corporation ("Enviri")"
    # is not); an acronym stands for its legal name's initials ("BD" = Becton,
    # Dickinson; "MSG Sports" = Madison Square Garden Sports Corp.)
    s0 = short.split()[0]
    initials = "".join(w[0] for w in re.findall(r"[A-Za-z]+", full)).upper()
    if full != short and s0.lower() not in full.lower() and not (s0.isupper() and initials.startswith(s0)):
        full = short
    for nm in (full, short):
        n = norm(nm)
        tk = idx.get(n) or cidx.get(n.replace(" ", ""))
        if tk:
            return full, tk
    n = norm(short)
    if len(n) >= 4:                     # "Honeywell" -> HONEYWELL INTERNATIONAL (the held listing first)
        hits = sorted((k for k in idx if k == n or k.startswith(n + " ")), key=len)
        if hits:
            return full, idx[hits[0]]
    return full, None

def spin_parent(text, registrant, idx, cidx):
    """(parent, parent ticker, merger note) for a Form 10 information
    statement, or (None, None, "") when no company distributes the shares."""
    from map_pb_tickers import norm
    t = text[:400000]
    own = norm(registrant)
    cnt = {}
    def add(nm, w):
        nm = re.sub(r"\s*\([^)]*\)", "", nm).strip(" ,")
        nm = re.sub(r"^(?:The|the) ", "", nm)                  # "The Middleby Corporation"
        nm = re.sub(r",? (?:Inc\.?|Corporation|Corp\.?|Company|plc|Ltd\.?|Limited)$", "", nm)
        if not nm or nm.lower() in _NOT_PARENT or nm.split()[0].lower() in ("future", "fellow") \
                or norm(nm) == own or len(nm) < 2 or re.fullmatch(_SUFFIX_ONLY, nm):
            return
        cnt[nm] = cnt.get(nm, 0) + w
    for m in _DEAR.finditer(t):
        d = m.group(1)
        q = re.search(r"[“\"]([^”\"]{1,40})[”\"]", d)       # Dear Resideo Technologies, Inc. ("Resideo") Stockholder
        add(q.group(1) if q else d, 3)
    for i, m in enumerate(_DIST.finditer(t)):
        if i >= 8:
            break
        add(m.group(1), 1)
    if not cnt:
        return None, None, ""
    # a label run into the name ("Distributed Securities Comcast will
    # distribute") votes for the name it ends with
    for c in sorted(cnt, key=len):
        for d in list(cnt):
            if d != c and d.endswith(" " + c) and cnt.get(d):
                cnt[c] += cnt.pop(d)
    short = max(cnt, key=cnt.get)
    parent, tk = _resolve(short, t, idx, cidx)
    merge = ""
    if "Merger Agreement" in t:          # a Reverse Morris Trust: the spun-off unit merges into a buyer
        acq = [m.group(1) for m in _ACQ.finditer(t) if m.group(1) != short and m.group(1).lower() not in _NOT_PARENT]
        if acq:
            a_full, a_tk = _resolve(max(set(acq), key=acq.count), t, idx, cidx)
            merge = f" · then merging into {a_full}" + (f" ({a_tk})" if a_tk else "")
    return parent, tk, merge

def parent_ticker(detail):
    """The spin-off parent's ticker from a sec_events detail ("parent
    Honeywell International Inc. (HON)")."""
    m = re.match(r"parent [^()]*?\(([A-Z0-9.\-]+)\)", detail or "")
    return m.group(1) if m else None

def form3_role(cik, adsh, docs):
    """'Director', 'CEO', '10% owner'... from the Form 3 XML; None when EDGAR
    would not serve it."""
    xml = next((d for d in docs if d.endswith(".xml")), None)
    if not xml:
        return ""
    t = curl(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/{xml}").decode("utf-8", "ignore")
    if not t.strip():
        return None
    role = []
    if re.search(r"<isDirector>\s*(1|true)\s*</isDirector>", t, re.I):
        role.append("Director")
    m = re.search(r"<officerTitle>\s*([^<]+?)\s*</officerTitle>", t)
    if re.search(r"<isOfficer>\s*(1|true)\s*</isOfficer>", t, re.I):
        role.append(html.unescape(m.group(1)) if m else "Officer")
    if re.search(r"<isTenPercentOwner>\s*(1|true)\s*</isTenPercentOwner>", t, re.I):
        role.append("10% owner")
    return ", ".join(role)

def run():
    import ingest_13d as i13
    from map_pb_tickers import build_index, norm
    conn = sqlite3.connect(DB, timeout=120); conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("""CREATE TABLE IF NOT EXISTS sec_events (
        kind TEXT, form TEXT, filed TEXT, accession TEXT PRIMARY KEY,
        subject_cik TEXT, subject_name TEXT, subject_ticker TEXT,
        party_cik TEXT, party_name TEXT, detail TEXT)""")
    tj, how = company_tickers()
    tick_by_cik = i13.primary_ticker_by_cik(tj) if tj else {}
    if how != "fresh":
        print(f"  ! SEC ticker list not served: using the {how}", flush=True)
    idx, cidx = build_index(conn)
    # tracked people (the people monitor) and roster funds, for Form 3
    people = {}
    for full, first, last in conn.execute("SELECT full_name, first_name, last_name FROM pb_people"):
        if first and last:
            people[(norm(last), norm(first).split(" ")[0])] = full
    today = dt.date.today()
    failed = 0
    for kind, forms in FORMS.items():
        start = (today - dt.timedelta(days=WINDOW[kind])).isoformat()
        rows = []
        for form in forms:
            res = search(form, start, today.isoformat())
            if res is None:
                failed += 1
                print(f"  ! {kind}/{form}: search failed — window kept as it was", flush=True)
                rows = None
                break
            for adsh, docs in res.items():
                if not adsh:
                    continue
                src = docs[0]
                ps = parties(src, tick_by_cik)
                if not ps:
                    continue
                if kind == "form3":
                    # the person or fund files; the company is the other party
                    comp = next((p for p in ps if p[1]), ps[-1])
                    other = next((p for p in ps if p is not comp), None)
                else:
                    comp = next((p for p in ps if p[1]), ps[0])
                    other = next((p for p in ps if p is not comp), None)
                rows.append([kind, src.get("form"), src.get("file_date"), adsh, comp[2], comp[0],
                             (comp[1] or [None])[0], other[2] if other else None, other[0] if other else None,
                             "", [d.get("_id", "").split(":")[-1] for d in docs],
                             [d.get("file_type") for d in docs]])
            time.sleep(0.2)
        if rows is None:
            continue
        # a document EDGAR won't serve today keeps the reading an earlier run made
        old = {a: (p, pn, d) for a, p, pn, d in conn.execute(
            "SELECT accession, party_cik, party_name, detail FROM sec_events WHERE kind = ?", (kind,))}
        unread = 0
        # detail: the spin-off's parent; the Form 3 insider's role (tracked people)
        if kind == "spin":
            # the information statement is usually EX-99.1, sometimes the
            # Form 10 itself; an amendment may carry only exhibits: read up
            # to four documents, newest filing first, until a parent is named
            def rank(ty):
                ty = (ty or "").upper()
                return 0 if ty == "EX-99.1" else 1 if ty.startswith("10-12") else 2 if ty.startswith("EX-99") else 9
            by_reg = {}
            for r in rows:
                by_reg.setdefault(r[4], []).append(r)
            parent_of = {}
            for cik, rs in by_reg.items():
                cands = sorted(((rank(ty), -int((r[2] or "0000-00-00").replace("-", "")), r[3], d, r[5])
                                for r in rs for d, ty in zip(r[10], r[11]) if rank(ty) < 9 and d))
                got, failed = (None, None, ""), False
                for _, _, adsh, doc, name in cands[:4]:
                    text = text_of(cik, adsh, doc)
                    time.sleep(0.2)
                    if text is None:
                        failed = True
                        continue
                    got = spin_parent(text, name, idx, cidx)
                    if got[0]:
                        break
                parent_of[cik] = "unread" if failed and not got[0] else got
            prev_of = {}                               # an earlier run's reading, per registrant
            for r in rows:
                o = old.get(r[3])
                if o and o[2] and not o[2].startswith("parent not read"):
                    prev_of.setdefault(r[4], o)
            for r in rows:
                got = parent_of.get(r[4], (None, None, ""))
                if got == "unread":
                    o = prev_of.get(r[4])
                    if o:
                        r[7], r[8], r[9] = o
                    else:
                        r[7], r[8] = None, None
                        r[9] = "parent not read: EDGAR did not serve the filing (retried next run)"
                        unread += 1
                    continue
                parent, tk, merge = got
                r[7], r[8] = None, parent
                r[9] = (f"parent {parent}" + (f" ({tk})" if tk else "") + merge) if parent \
                    else "no parent named: a fund, an uplisting or a holding-company formation"
        if kind == "form3":
            for r in rows:
                nm = r[8] or ""
                w = [x for x in re.sub(r"[^A-Za-z ]", " ", nm).upper().split()
                     if x not in ("JR", "SR", "II", "III", "IV")]
                hit = people.get((norm(w[0]), norm(w[1]))) if len(w) >= 2 else None
                if hit:
                    role = form3_role(r[4], r[3], r[10])
                    if role is None:
                        o = old.get(r[3])
                        if o and o[2] and o[2].startswith("tracked person") and "role not read" not in o[2]:
                            r[9] = o[2]
                            continue
                        unread += 1
                        r[9] = f"tracked person: {hit} · role not read (EDGAR did not serve the filing)"
                        continue
                    r[9] = f"tracked person: {hit}" + (f" · {role}" if role else "")
                    time.sleep(0.15)
        conn.execute(f"DELETE FROM sec_events WHERE kind = ?", (kind,))
        conn.executemany("INSERT OR REPLACE INTO sec_events VALUES (?,?,?,?,?,?,?,?,?,?)", [r[:10] for r in rows])
        conn.commit()
        n_sub = len({r[4] for r in rows})
        extra = ""
        if kind == "spin":
            extra = f"; {sum(1 for r in rows if (r[9] or '').startswith('parent'))} filings name a parent"
        if kind == "form3":
            extra = f"; {sum(1 for r in rows if (r[9] or '').startswith('tracked'))} by tracked people"
        if unread:
            extra += f"; {unread} documents EDGAR would not serve (marked, retried next run)"
        print(f"{kind}: {len(rows):,} filings about {n_sub:,} companies in {WINDOW[kind]} days{extra}", flush=True)
    conn.close()
    return failed

if __name__ == "__main__":
    sys.exit(2 if run() else 0)
