"""Legal Metrology & Instrument Verification System (LMIVS) - Streamlit MVP.
Run:  pip install streamlit pandas pillow qrcode reportlab  &&  streamlit run app.py
"""
import hashlib, io
from datetime import date, timedelta

import pandas as pd
import qrcode
import streamlit as st
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

st.set_page_config(page_title="LMIVS - Legal Metrology", page_icon="⚖️", layout="wide")
S = st.session_state
SECRET = "LMIVS-SALT-2026"
TODAY = date.today()
TOL = {"I": 0.05, "II": 0.10, "III": 0.20, "IIII": 0.50}  # max permissible error % by accuracy class
STEPS = ["Submitted", "Scheduled", "In-Verification", "Verified"]
SLOTS = ["09:00-11:00", "11:00-13:00", "14:00-16:00", "16:00-18:00"]
H = lambda s: hashlib.sha256(s.encode()).hexdigest()

st.markdown("""<style>
.block-container{padding-top:1.2rem;max-width:1200px}
@media(max-width:640px){.block-container{padding:.6rem}.stButton>button{width:100%;min-height:3rem}
[data-testid="stMetricValue"]{font-size:1.4rem}}
.pill{padding:2px 10px;border-radius:12px;background:#e8f0fe;font-size:.8rem}
</style>""", unsafe_allow_html=True)

# ---------------------------------------------------------------- data layer
def init():
    if "users" in S: return
    S.users = pd.DataFrame([
        ["applicant", "Rajesh Traders Pvt Ltd", "Applicant", "Jhajjar, Haryana", "rajesh@traders.in", H("applicant123")],
        ["lmo", "Anita Sharma", "LMO", "Jhajjar District Office", "anita.sharma@lm.gov.in", H("lmo123")],
        ["gatc", "Vikram Singh", "GATC Inspector", "GATC-Rohtak Test Center", "vikram@gatc.in", H("gatc123")],
        ["admin", "System Administrator", "Admin", "State Controller HQ", "admin@lm.gov.in", H("admin123")],
    ], columns=["username", "name", "role", "jurisdiction", "email", "pw"])
    d = lambda n: TODAY + timedelta(days=n)
    S.inst = pd.DataFrame([
        ["I-1001", "applicant", "Platform Scale", "PS-88231", "500 kg", "Essae", "III", "Jhajjar Mandi", "Verified", d(-353), "calib_ps88231.pdf; site1.jpg", "lmo", d(-350), SLOTS[0]],
        ["I-1002", "applicant", "Weighbridge", "WB-11902", "40 t", "Avery", "III", "Bahadurgarh Yard", "Verified", d(-165), "calib_wb11902.pdf", "gatc", d(-160), SLOTS[1]],
        ["I-1003", "applicant", "Fuel Dispenser", "FD-7745", "99.99 L", "Tokheim", "II", "Sector 5 Fuel Pump", "Verified", d(-340), "calib_fd7745.pdf", "lmo", d(-338), SLOTS[2]],
        ["I-1004", "applicant", "Counter Scale", "CS-3310", "30 kg", "Libra", "II", "Jhajjar Market", "Submitted", d(-3), "calib_cs3310.pdf", "", None, ""],
        ["I-1005", "applicant", "Platform Scale", "PS-99120", "1000 kg", "Essae", "III", "Rohtak Godown", "Scheduled", d(-6), "calib_ps99120.pdf", "lmo", d(2), SLOTS[1]],
        ["I-1006", "applicant", "Milk Analyzer", "MA-4471", "10 L", "Afimilk", "I", "Dairy Unit 2", "In-Verification", d(-9), "calib_ma4471.pdf", "gatc", d(0), SLOTS[3]],
    ], columns=["inst_id", "owner", "type", "serial", "capacity", "make", "cls", "location", "status", "submitted", "docs", "officer", "sched_date", "slot"])
    S.ver = pd.DataFrame(columns=["inst_id", "loads", "errors", "max_err", "tol", "result", "remarks", "officer", "date", "photo"])
    S.certs = pd.DataFrame(columns=["cert_id", "inst_id", "serial", "issued", "valid_until", "hash", "revoked"])
    for iid, days in [("I-1001", -350), ("I-1002", -160), ("I-1003", -338)]:
        S.ver.loc[len(S.ver)] = [iid, "10/50/100%", "0.02/0.03/0.04", 0.04, TOL["III"], "Pass", "Baseline verification.", S.inst.set_index("inst_id").loc[iid, "officer"], TODAY + timedelta(days=days), None]
        issue_cert(iid, TODAY + timedelta(days=days))
    S.user = None
    S.audit = []

def issue_cert(iid, issued=None):
    issued = issued or TODAY
    row = S.inst.set_index("inst_id").loc[iid]
    cid = f"LMC-{issued.year}-{len(S.certs) + 1:04d}"
    valid = issued + timedelta(days=365)
    h = H(f"{cid}{row.serial}{issued}{valid}{SECRET}")[:16].upper()
    S.certs.loc[len(S.certs)] = [cid, iid, row.serial, issued, valid, h, False]
    return cid

def cert_status(c):
    if c.revoked: return "Revoked"
    left = (c.valid_until - TODAY).days
    return "Expired" if left < 0 else ("Expiring" if left <= 30 else "Active")

def payload(c):
    return f"LMIVS|VID:{c.cert_id}|SN:{c.serial}|ISS:{c.issued}|VALID:{c.valid_until}|AUTH:{c.hash}"

def qr_bytes(text):
    img = qrcode.make(text)
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return buf.getvalue()

def set_status(iid, status):
    S.inst.loc[S.inst.inst_id == iid, "status"] = status

def log(msg):
    S.audit.append(f"{pd.Timestamp.now():%Y-%m-%d %H:%M} | {S.user['name']} | {msg}")

def cert_pdf(c):
    inst = S.inst.set_index("inst_id").loc[c.inst_id]
    owner = S.users.set_index("username").loc[inst.owner, "name"]
    buf = io.BytesIO(); p = canvas.Canvas(buf, pagesize=A4); w, h = A4
    p.setStrokeColorRGB(.1, .2, .5); p.setLineWidth(3); p.rect(25, 25, w - 50, h - 50)
    p.setFont("Helvetica-Bold", 20); p.drawCentredString(w / 2, h - 80, "GOVERNMENT OF INDIA - LEGAL METROLOGY")
    p.setFont("Helvetica-Bold", 16); p.drawCentredString(w / 2, h - 110, "DIGITAL VERIFICATION CERTIFICATE")
    p.setFont("Helvetica", 10); p.drawCentredString(w / 2, h - 128, "Issued under the Legal Metrology Act, 2009")
    rows = [("Certificate / Verification ID", c.cert_id), ("Owner", owner), ("Instrument", inst.type),
            ("Serial No.", inst.serial), ("Make", inst.make), ("Capacity", inst.capacity),
            ("Accuracy Class", inst.cls), ("Location", inst.location), ("Date of Issue", str(c.issued)),
            ("Valid Until", str(c.valid_until)), ("Authentication Hash", c.hash), ("Status", cert_status(c))]
    y = h - 190
    for k, v in rows:
        p.setFont("Helvetica-Bold", 11); p.drawString(70, y, k + ":")
        p.setFont("Helvetica", 11); p.drawString(260, y, str(v)); y -= 26
    p.drawImage(ImageReader(io.BytesIO(qr_bytes(payload(c)))), w / 2 - 70, y - 160, 140, 140)
    p.setFont("Helvetica-Oblique", 9); p.drawCentredString(w / 2, y - 175, "Scan QR code to verify authenticity")
    p.setFont("Helvetica", 9); p.drawCentredString(w / 2, 60, "Computer-generated certificate. Digitally hashed (SHA-256).")
    p.showPage(); p.save()
    return buf.getvalue()

@st.dialog("Digital Verification Certificate")
def cert_dialog(cid):
    c = S.certs[S.certs.cert_id == cid].iloc[0]
    inst = S.inst.set_index("inst_id").loc[c.inst_id]
    a, b = st.columns([2, 1])
    a.markdown(f"**ID:** {c.cert_id}  \n**Instrument:** {inst.type} ({inst.make})  \n**Serial:** {c.serial}  \n"
               f"**Class:** {inst.cls}  \n**Issued:** {c.issued}  \n**Valid until:** {c.valid_until}  \n"
               f"**Status:** {cert_status(c)}  \n**Hash:** `{c.hash}`")
    b.image(Image.open(io.BytesIO(qr_bytes(payload(c)))), caption="Verification QR")
    st.download_button("⬇️ Download PDF", cert_pdf(c), f"{c.cert_id}.pdf", "application/pdf", key="dl_" + cid)

# ---------------------------------------------------------------- auth
def login_ui():
    st.title("⚖️ Legal Metrology & Instrument Verification System")
    st.caption("Sign in to continue. Demo accounts: applicant / lmo / gatc / admin  (password = role + 123)")
    with st.container(border=True):
        u = st.selectbox("User", S.users.username)
        pw = st.text_input("Password", type="password")
        if st.button("Login", type="primary"):
            row = S.users[S.users.username == u].iloc[0]
            if H(pw) == row.pw:
                S.user = row.to_dict(); st.rerun()
            else:
                st.error("Invalid credentials.")

def alerts_for(user):
    out = []
    ids = S.inst.inst_id if user["role"] != "Applicant" else S.inst[S.inst.owner == user["username"]].inst_id
    for _, c in S.certs[S.certs.inst_id.isin(ids)].iterrows():
        left = (c.valid_until - TODAY).days
        if left < 0: out.append(("🔴", f"Certificate {c.cert_id} ({c.serial}) EXPIRED {-left} days ago."))
        elif left <= 30: out.append(("🟠", f"Certificate {c.cert_id} ({c.serial}) expires in {left} days."))
    ins = S.inst[S.inst.inst_id.isin(ids)]
    r = user["role"]
    if r in ("Admin", "LMO"):
        n = (ins.status == "Submitted").sum()
        if n: out.append(("🟡", f"{n} application(s) awaiting scheduling."))
    if r in ("LMO", "GATC Inspector", "Admin"):
        mine = ins[ins.status.isin(["Scheduled", "In-Verification"])]
        if r != "Admin": mine = mine[mine.officer == user["username"]]
        for _, i in mine.iterrows(): out.append(("🔵", f"Verification pending: {i.inst_id} {i.type} on {i.sched_date} {i.slot}."))
    if r == "Applicant":
        for _, i in ins[ins.status == "Rejected"].iterrows(): out.append(("🔴", f"{i.inst_id} was rejected - re-register after adjustment."))
    return out

# ---------------------------------------------------------------- pages
def pg_dashboard():
    st.header("📊 Analytics Dashboard")
    c = S.certs.copy(); c["st"] = c.apply(cert_status, axis=1)
    m = st.columns(4)
    m[0].metric("Total Verified", int((S.inst.status == "Verified").sum()))
    m[1].metric("Pending Reviews", int(S.inst.status.isin(["Submitted", "Scheduled", "In-Verification"]).sum()))
    m[2].metric("Expiring ≤ 30 Days", int((c.st == "Expiring").sum()))
    m[3].metric("Rejections", int((S.inst.status == "Rejected").sum()))
    a, b = st.columns(2)
    a.subheader("Instruments by status"); a.bar_chart(S.inst.status.value_counts())
    b.subheader("Instruments by type"); b.bar_chart(S.inst.type.value_counts())
    st.subheader("Recent activity"); st.dataframe(pd.DataFrame({"Audit log": S.audit[::-1][:10] or ["No activity this session"]}), use_container_width=True, hide_index=True)

def pg_register():
    st.header("📝 Register Instrument")
    me = S.user["username"]
    with st.form("reg", clear_on_submit=True):
        c1, c2 = st.columns(2)
        t = c1.selectbox("Instrument Type", ["Platform Scale", "Counter Scale", "Weighbridge", "Fuel Dispenser", "Milk Analyzer", "Measuring Tape", "Taxi Meter"])
        sn = c2.text_input("Serial No.*"); cap = c1.text_input("Capacity*", placeholder="e.g. 500 kg")
        mk = c2.text_input("Make*"); cl = c1.selectbox("Accuracy Class", list(TOL)); loc = c2.text_input("Installation Location*")
        cal = st.file_uploader("Calibration report(s)", type=["pdf", "png", "jpg"], accept_multiple_files=True)
        ph = st.file_uploader("Site photograph(s)", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
        if st.form_submit_button("Submit Application", type="primary"):
            if not (sn and cap and mk and loc): st.error("Fill all mandatory (*) fields.")
            elif (S.inst.serial == sn).any(): st.error("Serial number already registered.")
            else:
                iid = f"I-{1001 + len(S.inst)}"
                docs = "; ".join([f.name for f in cal + ph]) or "-"
                S.inst.loc[len(S.inst)] = [iid, me, t, sn, cap, mk, cl, loc, "Submitted", TODAY, docs, "", None, ""]
                log(f"Registered {iid}"); st.success(f"Application {iid} submitted."); 
    st.subheader("My Instruments")
    st.dataframe(S.inst[S.inst.owner == me].drop(columns=["owner"]), use_container_width=True, hide_index=True)

def pg_tracker():
    st.header("🛰️ Application Tracker")
    df = S.inst if S.user["role"] != "Applicant" else S.inst[S.inst.owner == S.user["username"]]
    for _, i in df.iterrows():
        with st.container(border=True):
            rej = i.status == "Rejected"
            idx = 2 if rej else STEPS.index(i.status)
            st.markdown(f"**{i.inst_id}** · {i.type} · `{i.serial}` &nbsp; <span class='pill'>{i.status}</span>", unsafe_allow_html=True)
            st.progress((idx + 1) / 4)
            labels = STEPS[:3] + ["Rejected" if rej else "Verified"]
            st.caption(" → ".join(f"**{l}**" if k <= idx else l for k, l in enumerate(labels)))
            if i.sched_date: st.caption(f"📅 {i.sched_date} {i.slot} · Officer: {i.officer or '-'}")

def pg_schedule():
    st.header("🗓️ Scheduling")
    officers = S.users[S.users.role.isin(["LMO", "GATC Inspector"])]
    pend = S.inst[S.inst.status == "Submitted"]
    if pend.empty: st.info("No applications awaiting scheduling.")
    else:
        with st.form("sch"):
            iid = st.selectbox("Application", pend.inst_id, format_func=lambda x: f"{x} - {pend.set_index('inst_id').loc[x, 'type']}")
            c1, c2, c3 = st.columns(3)
            dt = c1.date_input("Verification date", TODAY + timedelta(days=3), min_value=TODAY)
            sl = c2.selectbox("Slot", SLOTS)
            off = c3.selectbox("Officer", officers.username, format_func=lambda u: f"{officers.set_index('username').loc[u, 'name']} ({officers.set_index('username').loc[u, 'role']})")
            if st.form_submit_button("Assign & Schedule", type="primary"):
                clash = S.inst[(S.inst.officer == off) & (S.inst.sched_date == dt) & (S.inst.slot == sl)]
                if len(clash): st.error("Officer already booked for that slot.")
                else:
                    S.inst.loc[S.inst.inst_id == iid, ["officer", "sched_date", "slot"]] = [off, dt, sl]
                    set_status(iid, "Scheduled"); log(f"Scheduled {iid} -> {off} {dt} {sl}"); st.success("Scheduled."); st.rerun()
    st.subheader("Calendar")
    st.dataframe(S.inst[S.inst.sched_date.notna()][["inst_id", "type", "serial", "sched_date", "slot", "officer", "status"]].sort_values("sched_date"), use_container_width=True, hide_index=True)

def pg_verify():
    st.header("🔧 Field Verification")
    u = S.user
    q = S.inst[S.inst.status.isin(["Scheduled", "In-Verification"])]
    if u["role"] != "Admin": q = q[q.officer == u["username"]]
    if q.empty: return st.info("No verifications assigned to you.")
    iid = st.selectbox("Assigned job", q.inst_id, format_func=lambda x: f"{x} - {q.set_index('inst_id').loc[x, 'type']} @ {q.set_index('inst_id').loc[x, 'location']}")
    i = q.set_index("inst_id").loc[iid]
    st.write(f"**{i.type}** · S/N `{i.serial}` · Cap {i.capacity} · Class {i.cls} · Max permissible error ±{TOL[i.cls]}%")
    if i.status == "Scheduled":
        if st.button("▶️ Start Verification", type="primary"):
            set_status(iid, "In-Verification"); log(f"Started {iid}"); st.rerun()
        return
    with st.form("ver"):
        st.caption("Enter test points: applied standard value vs. instrument indication.")
        pts = []
        for k, pct in enumerate([10, 50, 100]):
            c1, c2 = st.columns(2)
            a = c1.number_input(f"Applied @ {pct}%", 0.0, value=float(pct), key=f"a{k}")
            b = c2.number_input(f"Indicated @ {pct}%", 0.0, value=float(pct), key=f"b{k}")
            pts.append((a, b))
        rem = st.text_area("Remarks")
        cam = st.camera_input("Capture site image (optional)")
        up = st.file_uploader("...or upload site image", type=["png", "jpg", "jpeg"])
        if st.form_submit_button("Submit Evaluation", type="primary"):
            errs = [round((b - a) / a * 100, 3) if a else 0.0 for a, b in pts]
            mx = max(abs(e) for e in errs); ok = mx <= TOL[i.cls]
            photo = (cam or up).getvalue() if (cam or up) else None
            S.ver.loc[len(S.ver)] = [iid, "/".join(str(p[0]) for p in pts), "/".join(map(str, errs)), mx, TOL[i.cls], "Pass" if ok else "Fail", rem, u["username"], TODAY, photo]
            if ok:
                set_status(iid, "Verified"); cid = issue_cert(iid); st.session_state["flash"] = f"✅ PASS (max error {mx}%). Certificate {cid} issued."
            else:
                set_status(iid, "Rejected"); st.session_state["flash"] = f"❌ FAIL (max error {mx}% > ±{TOL[i.cls]}%). Instrument rejected."
            log(f"Evaluated {iid}: {'Pass' if ok else 'Fail'}"); st.rerun()

def pg_repo():
    st.header("🗄️ Certificate Repository")
    c = S.certs.copy()
    if S.user["role"] == "Applicant":
        c = c[c.inst_id.isin(S.inst[S.inst.owner == S.user["username"]].inst_id)]
    c["status"] = c.apply(cert_status, axis=1)
    f1, f2, f3, f4 = st.columns(4)
    cid = f1.text_input("Certificate ID"); sn = f2.text_input("Serial No.")
    stt = f3.multiselect("Status", ["Active", "Expiring", "Expired", "Revoked"])
    win = f4.slider("Expiring within (days)", 0, 400, 400)
    if cid: c = c[c.cert_id.str.contains(cid, case=False)]
    if sn: c = c[c.serial.str.contains(sn, case=False)]
    if stt: c = c[c.status.isin(stt)]
    c = c[c.valid_until.apply(lambda d: (d - TODAY).days <= win)]
    st.dataframe(c.drop(columns=["revoked"]), use_container_width=True, hide_index=True)
    if not c.empty:
        pick = st.selectbox("Open certificate", c.cert_id)
        b1, b2 = st.columns(2)
        if b1.button("👁️ View certificate + QR"): cert_dialog(pick)
        b2.download_button("⬇️ Download PDF", cert_pdf(c[c.cert_id == pick].iloc[0]), f"{pick}.pdf", "application/pdf")
        if S.user["role"] == "Admin" and st.button("🚫 Revoke selected"):
            S.certs.loc[S.certs.cert_id == pick, "revoked"] = True; log(f"Revoked {pick}"); st.rerun()
    with st.expander("🔍 Authenticity checker (paste QR payload)"):
        t = st.text_input("QR payload")
        if t:
            try:
                p = dict(x.split(":", 1) for x in t.split("|")[1:])
                good = H(f"{p['VID']}{p['SN']}{p['ISS']}{p['VALID']}{SECRET}")[:16].upper() == p["AUTH"]
                known = ((S.certs.cert_id == p["VID"]) & (S.certs.hash == p["AUTH"])).any()
                st.success("Authentic certificate ✔") if good and known else st.error("Hash mismatch / unknown certificate ✘")
            except Exception:
                st.error("Malformed payload.")

def pg_alerts():
    st.header("🔔 Alerts")
    al = alerts_for(S.user)
    if not al: st.success("No alerts. All clear!")
    for ic, m in al: st.markdown(f"{ic} {m}")

def pg_profile():
    st.header("👤 Profile")
    u = S.user
    with st.container(border=True):
        st.subheader(u["name"]); st.write(f"**Role:** {u['role']}  \n**Username:** {u['username']}  \n**Email:** {u['email']}  \n**Jurisdiction / Center:** {u['jurisdiction']}")
    with st.form("pf"):
        em = st.text_input("Update email", u["email"])
        if st.form_submit_button("Save"):
            S.users.loc[S.users.username == u["username"], "email"] = em; S.user["email"] = em; st.success("Updated."); st.rerun()

def pg_users():
    st.header("🛠️ User Administration")
    st.dataframe(S.users.drop(columns=["pw"]), use_container_width=True, hide_index=True)
    with st.form("nu", clear_on_submit=True):
        c = st.columns(3); un = c[0].text_input("Username"); nm = c[1].text_input("Name"); rl = c[2].selectbox("Role", ["Applicant", "LMO", "GATC Inspector", "Admin"])
        c = st.columns(3); jr = c[0].text_input("Jurisdiction / Center"); em = c[1].text_input("Email"); pw = c[2].text_input("Password", type="password")
        if st.form_submit_button("Create user") and un and pw and not (S.users.username == un).any():
            S.users.loc[len(S.users)] = [un, nm, rl, jr, em, H(pw)]; log(f"Created user {un}"); st.rerun()
    st.subheader("Audit log"); st.code("\n".join(S.audit[::-1]) or "No entries")

DOCS = """
## 1. Software Architecture
**Pattern:** MVC mapped onto Streamlit's rerun model.
| Layer | Implementation |
|---|---|
| **Model** | Pandas DataFrames in `st.session_state` (`users`, `inst`, `ver`, `certs`); helper functions (`issue_cert`, `set_status`) enforce domain rules |
| **View** | `pg_*` functions render pages with tabs, metrics, forms, dialogs |
| **Controller** | Sidebar router + form callbacks mutate the model, then `st.rerun()` |

**Data flow:** `Applicant submits → Submitted → Admin/LMO schedules → Scheduled → Officer starts → In-Verification → evaluation (error % vs class tolerance) → Verified (certificate + QR) or Rejected`.

**Workflow rule:** max |error %| across test points ≤ tolerance for accuracy class (I 0.05, II 0.10, III 0.20, IIII 0.50).

**Certificates:** ID `LMC-YYYY-NNNN`, 365-day validity, QR payload `LMIVS|VID|SN|ISS|VALID|AUTH`; PDF rendered by ReportLab with in-memory QR (PIL).

## 2. Security Framework
- **RBAC:** each role has a whitelist of pages (`MENU`); applicants see only own records; revocation and user admin are Admin-only.
- **Hash authentication:** passwords stored as SHA-256 digests; certificate authenticity via truncated SHA-256 over `ID+Serial+Issue+Valid+secret salt`, re-computed by the Authenticity Checker.
- **Auditability:** every state change is appended to the audit log. Slot double-booking is blocked.
- **Production hardening:** replace SHA-256 with bcrypt/argon2, move the salt to secrets, use HTTPS/SSO, persist to PostgreSQL, store files in object storage.

## 3. Deployment Methodology
1. `pip install streamlit pandas pillow qrcode reportlab`
2. Local: `streamlit run app.py`
3. Container: `FROM python:3.11-slim`, copy `app.py`, `EXPOSE 8501`, `CMD streamlit run app.py --server.address 0.0.0.0`
4. Cloud: Streamlit Community Cloud / Cloud Run / Kubernetes behind an HTTPS reverse proxy; put secrets in `st.secrets`.
5. Scale-out: swap session DataFrames for a shared DB so multiple users see the same state.
"""
def pg_docs():
    st.header("📚 Technical Documentation")
    t1, t2, t3 = st.tabs(["Architecture & Security & Deployment", "Roles & Permissions", "Data Dictionary"])
    t1.markdown(DOCS)
    t2.dataframe(pd.DataFrame({"Role": list(MENU), "Pages": [", ".join(MENU[r]) for r in MENU]}), hide_index=True, use_container_width=True)
    t3.dataframe(pd.DataFrame({t: [", ".join(getattr(S, k).columns)] for t, k in [("users", "users"), ("instruments", "inst"), ("verifications", "ver"), ("certificates", "certs")]}).T.rename(columns={0: "Columns"}), use_container_width=True)

PAGES = {"📊 Dashboard": pg_dashboard, "📝 Register Instrument": pg_register, "🛰️ Tracker": pg_tracker,
         "🗓️ Scheduling": pg_schedule, "🔧 Verification": pg_verify, "🗄️ Repository": pg_repo,
         "🔔 Alerts": pg_alerts, "👤 Profile": pg_profile, "🛠️ Users & Audit": pg_users, "📚 Technical Documentation": pg_docs}
MENU = {
    "Applicant": ["📝 Register Instrument", "🛰️ Tracker", "🗄️ Repository", "🔔 Alerts", "👤 Profile", "📚 Technical Documentation"],
    "LMO": ["📊 Dashboard", "🗓️ Scheduling", "🔧 Verification", "🛰️ Tracker", "🗄️ Repository", "🔔 Alerts", "👤 Profile", "📚 Technical Documentation"],
    "GATC Inspector": ["🔧 Verification", "🛰️ Tracker", "🗄️ Repository", "🔔 Alerts", "👤 Profile", "📚 Technical Documentation"],
    "Admin": ["📊 Dashboard", "🗓️ Scheduling", "🔧 Verification", "🛰️ Tracker", "🗄️ Repository", "🔔 Alerts", "🛠️ Users & Audit", "👤 Profile", "📚 Technical Documentation"],
}

# ---------------------------------------------------------------- main
init()
if not S.user:
    login_ui(); st.stop()

with st.sidebar:
    st.title("⚖️ LMIVS")
    st.write(f"**{S.user['name']}**  \n{S.user['role']} · {S.user['jurisdiction']}")
    n = len(alerts_for(S.user))
    if n: st.warning(f"🔔 {n} active alert(s)")
    page = st.radio("Navigate", MENU[S.user["role"]])
    st.divider()
    st.caption("Quick role switch (demo)")
    names = S.users.username.tolist()
    sw = st.selectbox("Switch to", names, index=names.index(S.user["username"]), label_visibility="collapsed")
    if sw != S.user["username"]:
        S.user = S.users[S.users.username == sw].iloc[0].to_dict(); st.rerun()
    if st.button("Logout"): S.user = None; st.rerun()

if S.get("flash"):
    st.info(S.pop("flash"))
if page not in MENU[S.user["role"]]:  # RBAC guard
    st.error("Access denied.")
else:
    PAGES[page]()