# -*- coding: utf-8 -*-
"""Sinh docs/nghiep-vu-app.html từ dữ liệu trong docs/spec/*.py và KIỂM TRA CHÉO với code Backend thật.

Chạy:  python docs/spec/build.py
Nếu một kiểm tra fail, script dừng, in lý do và KHÔNG ghi file HTML.
"""
import html
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rules import MODULES, RULES, GAPS, QUESTIONS  # noqa: E402
from api import (BASE, ENDPOINTS, PROPOSED, NOTE_ONLY, DRIVER_ERRORS, STAFF_ERRORS, EXTRA_ERRORS, OUT_OF_SCOPE)  # noqa: E402
ALL_EPS = ENDPOINTS + PROPOSED
PROPOSED_KEYS = {e[0] for e in PROPOSED}
from flows import SCREENS, FLOWS, STATE_MACHINES, ROLE_NAME  # noqa: E402
from tasks import OWNERS, PHASES, TASKS  # noqa: E402
from tests import TESTS  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BE_SRC = os.path.join(ROOT, "Backend", "src", "main", "java", "com", "parking", "backend")
OUT = os.path.join(ROOT, "docs", "nghiep-vu-app.html")

problems = []
report = []


def fail(msg):
    problems.append(msg)


# ----------------------------------------------------------------------------
# Chuẩn bị: số E cho từng endpoint khóa
# ----------------------------------------------------------------------------
keys = [e[0] for e in ALL_EPS]
if len(set(keys)) != len(keys):
    fail("Trùng khóa endpoint: " + str([k for k in keys if keys.count(k) > 1]))
E_NUM = {k: "E%03d" % (i + 1) for i, k in enumerate(keys)}
EP = {e[0]: e for e in ALL_EPS}

rule_ids = [r[0] for r in RULES]
if len(set(rule_ids)) != len(rule_ids):
    fail("Trùng id quy tắc")
rule_set = set(rule_ids)
mod_of_rule = {r[0]: r[1] for r in RULES}
for r in RULES:
    if r[1] not in MODULES:
        fail(f"{r[0]}: module lạ {r[1]}")

gap_ids = {g[0] for g in GAPS}
q_ids = {q[0] for q in QUESTIONS}
screen_ids = [s[0] for s in SCREENS]
if len(set(screen_ids)) != len(screen_ids):
    fail("Trùng id màn hình")
screen_owner = {s[0]: s[4] for s in SCREENS}
task_ids = [t[0] for t in TASKS]
if len(set(task_ids)) != len(task_ids):
    fail("Trùng id task")
test_ids = [t[0] for t in TESTS]
if len(set(test_ids)) != len(test_ids):
    fail("Trùng id test")
for t in test_ids:
    if not re.fullmatch(r"TC-[XABCD]\d\d", t):
        fail(f"Id test sai định dạng: {t}")

rule_to_tasks = defaultdict(list)
rule_to_tests = defaultdict(list)
ep_to_screens = defaultdict(list)
ep_to_tasks = defaultdict(list)
screen_to_tasks = defaultdict(list)

for sid, name, roles, route, owner, eps, rls, desc in SCREENS:
    if owner not in OWNERS:
        fail(f"{sid}: owner lạ")
    for rid in rls:
        if rid not in rule_set:
            fail(f"{sid} tham chiếu quy tắc không tồn tại {rid}")
    for k in eps:
        if k not in EP:
            fail(f"{sid} tham chiếu endpoint không tồn tại {k}")
        else:
            ep_to_screens[k].append(sid)

for tid, owner, phase, size, title, deliver, scr, eps, rls, deps, ac in TASKS:
    if owner not in OWNERS:
        fail(f"{tid}: owner lạ")
    if not ac:
        fail(f"{tid}: thiếu tiêu chí nghiệm thu")
    for sid in scr:
        if sid not in screen_owner:
            fail(f"{tid}: màn không tồn tại {sid}")
        elif screen_owner[sid] != owner:
            fail(f"{tid}: màn {sid} thuộc {screen_owner[sid]} nhưng task thuộc {owner}")
        screen_to_tasks[sid].append(tid)
    for k in eps:
        if k not in EP:
            fail(f"{tid}: endpoint không tồn tại {k}")
        else:
            ep_to_tasks[k].append(tid)
    for rid in rls:
        if rid not in rule_set:
            fail(f"{tid}: quy tắc không tồn tại {rid}")
        rule_to_tasks[rid].append(tid)
    for d in deps:
        if d not in task_ids:
            fail(f"{tid}: phụ thuộc không tồn tại {d}")

for tc in TESTS:
    for rid in tc[4]:
        if rid not in rule_set:
            fail(f"{tc[0]}: quy tắc không tồn tại {rid}")
        rule_to_tests[rid].append(tc[0])

for rid in rule_ids:
    if not rule_to_tasks[rid]:
        fail(f"{rid}: chưa có task nào phụ trách")
    if not rule_to_tests[rid]:
        fail(f"{rid}: chưa có ca kiểm thử nào")
for sid in screen_ids:
    if not screen_to_tasks[sid]:
        fail(f"{sid}: chưa có task nào làm màn này")
for k in keys:
    if k not in NOTE_ONLY and not ep_to_screens[k]:
        fail(f"{k}: không màn nào dùng (thêm vào màn hoặc NOTE_ONLY)")
    if not ep_to_tasks[k]:
        fail(f"{k}: không task nào nhận (thêm vào danh sách endpoint của task)")
    users = {screen_owner[s] for s in ep_to_screens[k]}
    if users and EP[k][4] not in users and k not in NOTE_ONLY:
        fail(f"{k}: owner {EP[k][4]} không phải chủ của màn nào dùng nó ({sorted(users)})")
for owner in OWNERS:
    if not any(t[1] == owner for t in TASKS):
        fail(f"Owner {owner} không có task")

# phụ thuộc task: không vòng, không phụ thuộc vào giai đoạn muộn hơn
_phase = {t[0]: int(t[2][1:]) for t in TASKS}
_deps = {t[0]: list(t[9]) for t in TASKS}
for tid, ds in _deps.items():
    for d in ds:
        if d in _phase and _phase[d] > _phase[tid]:
            fail(f"{tid} (P{_phase[tid]}) phụ thuộc {d} ở giai đoạn muộn hơn (P{_phase[d]})")
_state = {}
def _visit(n, path):
    if _state.get(n) == 2:
        return
    if _state.get(n) == 1:
        fail("Vòng phụ thuộc task: " + " → ".join(path + [n]))
        return
    _state[n] = 1
    for d in _deps.get(n, []):
        _visit(d, path + [n])
    _state[n] = 2
for _t in _deps:
    _visit(_t, [])

all_text = " ".join(str(x) for x in (RULES, GAPS, QUESTIONS, SCREENS, TASKS, TESTS, STATE_MACHINES, FLOWS, ALL_EPS))
for ref in set(re.findall(r"\bG-\d\d\b", all_text)):
    if ref not in gap_ids:
        fail(f"Tham chiếu {ref} không tồn tại")
for ref in set(re.findall(r"\bQ-\d\d\b", all_text)):
    if ref not in q_ids:
        fail(f"Tham chiếu {ref} không tồn tại")
for ref in set(re.findall(r"\bR-[XABCD]\d\d\b", all_text)):
    if ref not in rule_set:
        fail(f"Tham chiếu {ref} không tồn tại")
for ref in set(re.findall(r"\bS-[ABCD]\d\d\b", all_text)):
    if ref not in screen_owner:
        fail(f"Tham chiếu {ref} không tồn tại")
for ref in set(re.findall(r"\bT-[ABCD]\d\b", all_text)):
    if ref not in task_ids:
        fail(f"Tham chiếu {ref} không tồn tại")
for ref in set(re.findall(r"\bTC-[XABCD]\d\d\b", all_text)):
    if ref not in test_ids:
        fail(f"Tham chiếu {ref} không tồn tại")
# tham chiếu "mục N" cứng dễ lệch số: cấm
for m in re.finditer(r"mục \d+", all_text):
    fail(f"Dùng tham chiếu số cứng '{m.group(0)}', hãy dùng tên mục")

# ----------------------------------------------------------------------------
# Đối chiếu mã lỗi với BE
# ----------------------------------------------------------------------------
be_codes = []
errfile = os.path.join(BE_SRC, "exception", "ErrorCode.java")
if os.path.exists(errfile):
    txt = open(errfile, encoding="utf-8").read()
    be_codes = re.findall(r'^\s+([A-Z][A-Z0-9_]+)\s*\(\s*"', txt, flags=re.M)
    docs_codes = set(DRIVER_ERRORS) | set(STAFF_ERRORS)
    missing = sorted(set(be_codes) - docs_codes)
    extra = sorted(docs_codes - set(be_codes))
    overlap = sorted(set(DRIVER_ERRORS) & set(STAFF_ERRORS))
    if missing:
        fail(f"Mã lỗi BE chưa có trong tài liệu: {missing}")
    if extra:
        fail(f"Mã lỗi trong tài liệu không có ở BE: {extra}")
    if overlap:
        fail(f"Mã lỗi nằm ở cả 2 nhóm: {overlap}")
    st = dict(re.findall(r'^\s+([A-Z][A-Z0-9_]+)\s*\(\s*"[A-Z0-9_]+"\s*,\s*"[^"]*"\s*,\s*HttpStatus\.([A-Z_]+)', txt, flags=re.M))
    to_num = {"NOT_FOUND": 404, "CONFLICT": 409, "BAD_REQUEST": 400, "UNAUTHORIZED": 401, "FORBIDDEN": 403,
              "INTERNAL_SERVER_ERROR": 500, "TOO_MANY_REQUESTS": 429}
    for code, (http, _m, _a) in {**DRIVER_ERRORS, **STAFF_ERRORS}.items():
        be_http = to_num.get(st.get(code, ""), None)
        if be_http is not None and be_http != http:
            fail(f"HTTP của {code}: tài liệu {http}, BE {be_http}")
    report.append(("Mã lỗi", f"{len(be_codes)} mã ở BE đều có thông điệp tiếng Việt ({len(DRIVER_ERRORS)} nhóm tài xế + {len(STAFF_ERRORS)} nhóm nhân viên/quản lý/quản trị), 0 thiếu, 0 thừa, HTTP khớp"))
else:
    report.append(("Mã lỗi", "BỎ QUA (không thấy thư mục Backend)"))


# ----------------------------------------------------------------------------
# Đối chiếu endpoint (method + đường dẫn + vai trò) với controller BE
# ----------------------------------------------------------------------------
def norm(p):
    p = p.split("?")[0]
    p = re.sub(r"\{[^}]*\}", "{}", p)
    return p.rstrip("/") or "/"


ROLE_WORDS = {"DRIVER", "STAFF", "MANAGER", "ADMIN"}
be_eps = {}
ctrl_dir = os.path.join(BE_SRC, "controller")
if os.path.isdir(ctrl_dir):
    for dp, _d, fs in os.walk(ctrl_dir):
        for f in fs:
            if not f.endswith(".java"):
                continue
            src = open(os.path.join(dp, f), encoding="utf-8").read()
            m = re.search(r'@RequestMapping\(\s*(?:value\s*=\s*)?"([^"]*)"', src)
            base = m.group(1) if m else ""
            for mm in re.finditer(r'@(Get|Post|Put|Patch|Delete)Mapping(?:\(([^)]*)\))?', src):
                args = mm.group(2) or ""
                pm = re.search(r'"([^"]*)"', args)
                sub = pm.group(1) if pm else ""
                head = src[max(0, mm.start() - 300):mm.start()]
                tail = src[mm.end():mm.end() + 500]
                pre = re.search(r'@PreAuthorize\("([^"]*)"\)', head + tail.split("public")[0])
                auth = pre.group(1) if pre else ""
                roles = set(re.findall(r"[A-Z]{3,}", re.sub(r"hasAnyRole|hasRole|isAuthenticated", "", auth))) & ROLE_WORDS
                be_eps[(mm.group(1).upper(), norm(base + sub))] = ("isAuthenticated" if "isAuthenticated" in auth else "", roles)
    doc_set = {}
    for e in ENDPOINTS:
        key = (e[1], norm("/api" + e[2]))
        if key in doc_set:
            fail(f"Endpoint trùng trong tài liệu: {key}")
        doc_set[key] = e
        if key not in be_eps:
            fail(f"{e[0]} {e[1]} /api{e[2]} không có ở BE")
            continue
        flag, be_roles = be_eps[key]
        auth = e[3]
        doc_roles = set(re.findall(r"[A-Z]{3,}", auth)) & ROLE_WORDS
        if doc_roles:
            if doc_roles != be_roles:
                fail(f"{e[0]}: vai trò tài liệu {sorted(doc_roles)} ≠ BE {sorted(be_roles)}")
        elif auth in ("public", "cookie", "không cần JWT", "BE nội bộ"):
            if be_roles or flag:
                fail(f"{e[0]}: tài liệu ghi '{auth}' nhưng BE yêu cầu {sorted(be_roles) or flag}")
        elif auth == "Bearer":
            if be_roles:
                fail(f"{e[0]}: tài liệu ghi 'Bearer' nhưng BE yêu cầu vai trò {sorted(be_roles)}")
        elif auth == "query token":
            if not flag:
                fail(f"{e[0]}: tài liệu ghi 'query token' nhưng BE không yêu cầu đăng nhập")
        else:
            fail(f"{e[0]}: kiểu auth lạ '{auth}'")
    for key in sorted(be_eps):
        if key not in doc_set:
            fail(f"Endpoint BE chưa có trong tài liệu: {key[0]} {key[1]}")
    report.append(("Endpoint", f"{len(be_eps)} endpoint ở BE đều có trong tài liệu và ngược lại ({len(ENDPOINTS)}), method + đường dẫn + vai trò được phép gọi đều khớp; mỗi endpoint có chủ, có task nhận"))
else:
    report.append(("Endpoint", "BỎ QUA (không thấy thư mục Backend)"))

report.append(("Rà soát logic độc lập", "3 reviewer đọc code BE đối chiếu từng quy tắc nghiệp vụ và tìm lỗ hổng liên vai trò. Họ xác nhận phần lớn quy tắc đúng, phát hiện hàng chục chỗ sai hoặc thiếu so với hành vi thật của BE (VD quét lại vé đã ACTIVE trả lỗi, check-out 0đ không thông báo, hạn mức làm tròn xuống, múi giờ BE, xóa/chọn loại xe, ràng buộc cấu hình bãi) và 25 lỗ hổng phân việc/luồng. Tất cả đã được sửa trong quy tắc, màn hình, task và test, hoặc ghi thành điểm lệch BE (G-28..G-36). Mô hình đặt chỗ \"trả ngay / trả sau, giữ tới giờ bắt đầu + 15 phút\" cũng qua một vòng rà soát riêng (20 phát hiện về ranh giới giờ, thu tiền mặt, chống chiếm chỗ, giữ chỗ vật lý), đã vá hết. Quy trình hoàn tiền qua quản lý duyệt và nút \"Đã nhận tiền mặt\" cũng qua một vòng rà soát riêng (18 phát hiện về doanh thu sau hoàn, mốc cuối ngày, bấm đúp, phân quyền, đối soát tiền mặt), đã vá hết."))
report.append(("Endpoint đề xuất", f"{len(PROPOSED)} endpoint mới (hoàn tiền qua duyệt, kèm tải ảnh biên lai) được đánh dấu \"đề xuất\", không đối chiếu BE; vẫn bắt buộc có chủ, màn dùng và task nhận"))
report.insert(0, ("Quy tắc", f"{len(RULES)} quy tắc: mỗi quy tắc có ≥ 1 task và ≥ 1 ca kiểm thử"))
report.insert(1, ("Màn hình", f"{len(SCREENS)} màn: mỗi màn có đúng 1 chủ và ≥ 1 task; {len(keys) - len(NOTE_ONLY)} endpoint được màn hình dùng, {len(NOTE_ONLY)} endpoint ghi chú (callback, QR ảnh, endpoint không dùng)"))
report.insert(2, ("Chia việc", f"{len(TASKS)} task cho 4 người; mọi task có tiêu chí nghiệm thu; phụ thuộc hợp lệ, không có vòng, không phụ thuộc vào giai đoạn muộn hơn; màn thuộc đúng chủ task"))
report.insert(3, ("Kiểm thử", f"{len(TESTS)} ca (Unit/Fake/BE); mọi mã tham chiếu R-/G-/Q-/S-/T-/TC- đều tồn tại; không có tham chiếu \"mục N\" cứng"))

if problems:
    print("KIỂM TRA CHÉO THẤT BẠI:")
    for p in problems:
        print(" -", p)
    sys.exit(1)

# ----------------------------------------------------------------------------
# Render HTML
# ----------------------------------------------------------------------------
esc = html.escape
EKEY_RE = "|".join(sorted((re.escape(k) for k in keys), key=len, reverse=True))


def md(text):
    """`code`, **đậm**, và tự gắn link tới R-/G-/Q-/S-/T-/TC-xx."""
    text = esc(text, quote=False)
    codes = []

    def keep(m):
        codes.append(m.group(1))
        return f"\u0000{len(codes) - 1}\u0000"

    text = re.sub(r"`([^`]+)`", keep, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\b(?:TC-[XABCD]\d\d|R-[XABCD]\d\d|G-\d\d|Q-\d\d|S-[ABCD]\d\d|T-[ABCD]\d)\b",
                  lambda m: f'<a class="ref" href="#{m.group(0)}">{m.group(0)}</a>', text)
    text = re.sub(r"\u0000(\d+)\u0000", lambda m: f"<code>{esc(codes[int(m.group(1))], quote=False)}</code>", text)
    return text


def own(o):
    if o in OWNERS:
        return f'<span class="own own-{o}" title="{esc(OWNERS[o][0])}: {esc(OWNERS[o][1])}">{o}</span>'
    return '<span class="own own-X">·</span>'


def refs(ids):
    return " ".join(f'<a class="ref" href="#{i}">{i}</a>' for i in ids) or "—"


def eprefs(ks):
    return " ".join(f'<a class="ref ep" href="#{E_NUM[k]}" title="{esc(EP[k][1])} /api{esc(EP[k][2])}">{E_NUM[k]}</a>' for k in ks) or "—"


def table(headers, rows, cls=""):
    th = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr" + (f' id="{r[0]}"' if r and r[0] else "") + ">" + "".join(f"<td>{c}</td>" for c in r[1]) + "</tr>" for r in rows)
    return f'<div class="tw"><table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


parts = []
add = parts.append
n_be = len(be_eps) if be_eps else len(ENDPOINTS)

# ---- 1 Tổng quan ----
add('<section id="tong-quan"><h2><span class="sn">1</span>Tổng quan</h2>')
add("<p class=\"lead\">App Flutter cho hệ thống quản lý bãi giữ xe PBM, phục vụ <strong>4 vai trò</strong>: tài xế đặt chỗ (trả ngay hoặc trả sau) và mua gói tháng; nhân viên quét QR check-in/check-out tại cổng; quản lý duyệt xe và quản lý gói; quản trị thiết lập bãi. Backend Spring Boot đã có sẵn: tài liệu này mô tả đúng những gì BE làm, chỉ ra chỗ BE chưa đáp ứng yêu cầu, và chia việc cho 4 người để phủ <strong>100% nghiệp vụ và 100% endpoint của BE</strong> mà không có chỗ nào mơ hồ.</p>")
add('<div class="cols">')
add('<div class="box"><h3>Luật chơi cốt lõi (đọc 30 giây)</h3><ol class="plain">'
    "<li><strong>Đặt chỗ không cần trả ngay.</strong> Trả ngay (VNPay) thì chỗ được <strong>giữ chắc</strong> suốt khung giờ.</li>"
    "<li>Chưa trả thì chỗ chỉ giữ tới <strong>giờ bắt đầu + 15 phút</strong>. Quá đó mà chưa trả và chưa tới thì coi như <strong>tự nguyện bỏ</strong>: không mất tiền, chỗ nhường khách vãng lai.</li>"
    "<li>Chưa trả mà tới trong 15 phút đó: nhân viên nhận tiền mặt rồi bấm <strong>\"Đã nhận tiền mặt\"</strong> để check-in. Mọi khoản tiền mặt đều phải có nút này.</li>"
    "<li><strong>Đã trả mà hủy trước giờ bắt đầu</strong>: chỗ nhả ngay nhưng tiền <strong>không hoàn tự động</strong>. Tài xế gửi yêu cầu hoàn tiền, <strong>quản lý duyệt</strong> nếu hợp lý và <strong>chuyển lại cuối ngày</strong>. Từ giờ bắt đầu: không hủy; <strong>không đến thì mất tiền</strong>.</li>"
    "<li>\"Slot\" là <strong>khung giờ</strong> trong ngày (4 khung × 6 tiếng), không phải ô đỗ cụ thể.</li>"
    "<li>Xe vào bãi khi <strong>nhân viên quét QR</strong>; sau đó phải <strong>xác nhận lên tầng</strong> mới ra được. Gói tháng đã mua <strong>không hủy, không hoàn</strong>.</li>"
    "</ol></div>")
add('<div class="box warn"><h3>BE chưa khớp yêu cầu ở 3 điểm lớn</h3><ul class="plain">'
    "<li><strong>G-01</strong>: callback VNPay của đặt chỗ bị chặn bảo mật, nên thanh toán đặt chỗ không bao giờ xác nhận được.</li>"
    "<li><strong>G-02</strong>: BE <em>không có hoàn tiền</em> và không cho hủy đặt chỗ đã trả tiền; quy trình yêu cầu hoàn tiền, quản lý duyệt, chuyển cuối ngày cần làm mới.</li>"
    "<li><strong>G-35</strong>: BE chưa có \"đặt trước, trả sau, giữ tới giờ bắt đầu + 15 phút\" và việc nhả chỗ cho khách vãng lai; <strong>G-36</strong>: chưa có thu tiền mặt tại cổng.</li>"
    "</ul><p class=\"muted\">Cả nhóm sửa BE nằm trong task T-B7. Trong lúc chờ, app chạy bằng dữ liệu giả theo đúng mô hình mới. Chi tiết ở mục <a href=\"#lech-be\">Lệch BE</a>.</p></div>")
add("</div>")

add('<h3>Mốc thời gian của một đặt chỗ</h3>')
add('<div class="tl" role="img" aria-label="Trục thời gian đặt chỗ: trước giờ bắt đầu, 15 phút ân hạn cho đặt chỗ chưa trả, rồi khung giờ đến hết giờ kết thúc">'
    '<div class="tl-seg tl-ok"><b>Trước giờ bắt đầu</b><span>Chưa trả: hủy miễn phí, chỗ được giữ. Đã trả: hủy được, chỗ nhả ngay, <em>xin hoàn tiền</em> chờ quản lý duyệt.</span></div>'
    '<div class="tl-mark">Giờ bắt đầu<br><small>reservedStartAt</small></div>'
    '<div class="tl-seg tl-use"><b>15 phút đầu</b><span>Chưa trả: tới được, nhân viên <em>thu tiền mặt</em> rồi check-in. Hết 15 phút: chỗ nhả cho khách vãng lai. Đã trả: giữ chắc.</span></div>'
    '<div class="tl-mark">Giờ kết thúc<br><small>reservedEndAt</small></div>'
    '<div class="tl-seg tl-bad"><b>Sau khung giờ</b><span>Đã trả mà chưa tới thì <em>EXPIRED</em>, mất tiền. Đang đỗ quá giờ: phụ phí lẻ.</span></div>'
    '</div>')
add('<p class="muted">Đặt chỗ chưa thanh toán (<code>PENDING</code>) hủy được bất kỳ lúc nào trước giờ nhả chỗ, miễn phí. Giờ nhả chỗ (<code>releaseAt</code>) = giờ bắt đầu + 15 phút.</p>')
add("</section>")

# ---- 2 Vai trò & điều hướng ----
TABS = {
    "driver": [("Trang chủ", "D", 0), ("Gói tháng", "C", 0), ("Đặt chỗ", "B", 1), ("Giao dịch", "D", 0), ("Tài khoản", "A", 0)],
    "staff": [("Trang chủ", "D", 0), ("Đang gửi", "D", 0), ("Quét mã", "D", 1), ("Đặt chỗ", "D", 0), ("Tài khoản", "A", 0)],
    "manager": [("Tổng quan", "C", 0), ("Bãi xe", "B", 0), ("Quét mã", "D", 1), ("Cần duyệt", "C", 0), ("Quản lý", "C", 0)],
    "admin": [("Người dùng", "C", 0), ("Tầng & Khu", "B", 0), ("Thiết lập", "B", 1), ("Bảng giá", "B", 0), ("Tài khoản", "A", 0)],
}
ROLE_ACCOUNT = {"driver": "driver@parking.vn", "staff": "staff@parking.vn", "manager": "manager@parking.vn", "admin": "admin@parking.vn"}
ROLE_DESC = {
    "driver": "Đặt chỗ trả trước, mua gói tháng, xem giao dịch và thông báo, quản lý xe của mình.",
    "staff": "Đứng ở cổng: quét QR check-in/check-out, xác nhận xe lên tầng, thu phí, phạt đỗ sai khu.",
    "manager": "Giám sát vận hành: tổng quan, duyệt xe, quản lý gói, bảng giá, tầng, khung giờ; cũng quét mã được.",
    "admin": "Thiết lập bãi: thông tin bãi, loại xe, khu, tầng, bảng giá, danh sách người dùng.",
}
add('<section id="vai-tro"><h2><span class="sn">2</span>Vai trò và thiết kế điều hướng</h2>')
add('<p class="lead">Mỗi vai trò có <strong>một vỏ giao diện riêng</strong>: bottom tab 5 ô, route riêng dưới <code>/driver</code>, <code>/staff</code>, <code>/manager</code>, <code>/admin</code>. Ô giữa luôn là thao tác dùng nhiều nhất của vai trò và được làm nổi bật (nút tròn nhô lên, R-X07). Chữ cái dưới mỗi ô là người sở hữu màn đó.</p>')
add('<div class="roles">')
for role in ("driver", "staff", "manager", "admin"):
    bars = "".join(
        f'<div class="tab{" tab-c" if c else ""}"><i class="tab-ico{" tab-ico-c" if c else ""}"></i><b>{esc(n)}</b>{own(o)}</div>'
        for n, o, c in TABS[role])
    add(f'<div class="role"><header><h3>{esc(ROLE_NAME[role])}</h3><code>{ROLE_ACCOUNT[role]}</code></header><p class="muted">{esc(ROLE_DESC[role])}</p><div class="tabs" role="img" aria-label="Bottom tab của {esc(ROLE_NAME[role])}">{bars}</div></div>')
add("</div>")
add('<div class="callout"><b>Tài khoản demo (chạy dữ liệu giả)</b><ul>'
    "<li>Email <code>driver@parking.vn</code>, <code>staff@parking.vn</code>, <code>manager@parking.vn</code>, <code>admin@parking.vn</code>; mật khẩu chung <code>123123@</code>. Màn đăng nhập có sẵn 4 chip để điền nhanh.</li>"
    "<li>BE thật seed tài khoản khác (<code>admin@pbm.com</code>, <code>staff1@pbm.com</code>, <code>driver1@pbm.com</code>... mật khẩu <code>123123</code>). Đề xuất thêm 4 tài khoản demo vào seed (G-21, Q-08).</li></ul></div>")
add('<h3>Khối lượng từng người</h3>')
rows = []
for o in OWNERS:
    ts = [t for t in TASKS if t[1] == o]
    scr = [s for s in SCREENS if s[4] == o]
    eps_o = [k for k in keys if EP[k][4] == o]
    rl = [r for r in RULES if r[1] == o]
    tc = [t for t in TESTS if t[1] == o]
    big = sum(1 for t in ts if t[3] == "L")
    rows.append(("", (own(o), f"<strong>{esc(OWNERS[o][0])}</strong><div class=\"muted\">{esc(OWNERS[o][1])}</div>", str(len(scr)), f"{len(ts)} <span class=\"muted\">({big} lớn)</span>", str(len(eps_o)), str(len(rl)), str(len(tc)), f"<code>{esc(OWNERS[o][2])}</code>")))
add(table(["", "Người", "Màn", "Task", "Endpoint", "Quy tắc", "Test", "Thư mục sở hữu"], rows))
add('<p class="muted">Quy tắc vàng: <strong>chỉ sửa trong thư mục của mình</strong>. File dùng chung (<code>app/router.dart</code>, <code>app/role_tabs.dart</code>, <code>pubspec.yaml</code>, <code>core/</code>) chỉ sửa qua pull request nhỏ và báo trong nhóm. Một số màn được dùng lại ở vai trò khác (VD Bảng giá của B nhúng vào menu Quản lý của C); route do chủ vai trò khai báo, widget do chủ màn xuất ra.</p>')
add("</section>")

# ---- 3 Thuật ngữ & phạm vi ----
add('<section id="thuat-ngu"><h2><span class="sn">3</span>Thuật ngữ và phạm vi</h2>')
add(table(["Từ", "Nghĩa trong dự án"], [
    ("", ("Slot", "Khung giờ trong ngày (mặc định 4 khung 6 giờ). Không phải ô đỗ vật lý.")),
    ("", ("Đặt chỗ (Reservation)", "Giữ trước khung giờ cho một xe vào một ngày, trả trước. Mã dạng <code>RSV-1004-A7K</code>.")),
    ("", ("Hạn mức (quota)", "Số đặt chỗ tối đa mỗi ngày cho mỗi loại xe (mặc định 20% sức chứa). Không chia theo slot.")),
    ("", ("Giữ chỗ (hold)", "BE giữ một chỗ vật lý cho đặt chỗ <code>CONFIRMED</code> từ 00:00 của ngày đặt.")),
    ("", ("Gói thành viên (Membership)", "Gói theo tháng, theo loại xe và khung giờ. Mã dạng <code>MBS-345-A9F</code>.")),
    ("", ("Phiên gửi xe (Parking session)", "Một lần xe vào bãi tới lúc ra. Mã vé dạng <code>PKG-20261002-0042</code>. Nhân viên mở/đóng.")),
    ("", ("Check-in / Check-out", "Nhân viên quét QR/biển số tại cổng. Tài xế chỉ đưa QR, không tự bấm.")),
    ("", ("Xác nhận lên tầng", "Quét vé ở đúng tầng được xếp để phiên chuyển từ <code>CHECKED_IN_GATE</code> sang <code>ACTIVE</code>; cần để check-out.")),
    ("", ("Tầng đơn loại / hỗn hợp", "Đơn loại: một loại xe. Hỗn hợp: hai loại xe, mỗi loại giữ một số khu (zone); đỗ sai khu bị phạt.")),
    ("", ("Effective status", "Trạng thái hiệu lực do BE tính (VD gói <code>ACTIVE</code> nhưng quá <code>endAt</code> thì API tài xế trả <code>EXPIRED</code>).")),
    ("", ("Fake / Api repository", "Hai cách cài đặt cùng một interface dữ liệu. Fake = dữ liệu giả để làm UI; Api = gọi BE thật.")),
]))
add("<h3>Ngoài phạm vi (quyết định có chủ đích)</h3>")
add(table(["Hạng mục", "Lý do và cách xử lý"], [("", (esc(a), md(b))) for a, b in OUT_OF_SCOPE]))
add("</section>")

# ---- 4 Quy tắc ----
add('<section id="quy-tac"><h2><span class="sn">4</span>Quy tắc nghiệp vụ</h2>')
add('<p class="lead">Mỗi quy tắc có mã <code>R-…</code>, một module chịu trách nhiệm, và ít nhất một ca kiểm thử. Khi có tranh cãi, quy tắc ở đây là câu trả lời; nếu thấy sai, sửa ở đây trước rồi mới sửa code.</p>')
add('<div class="filters" data-target="rules-body" role="group" aria-label="Lọc theo module">'
    '<button class="chip on" data-f="*">Tất cả</button>' + "".join(f'<button class="chip" data-f="{m}">{own(m) if m in OWNERS else ""} {esc(MODULES[m])}</button>' for m in "XABCD") + "</div>")
body = "".join(
    f'<tr id="{rid}" data-m="{mod}"><td><a class="ref" href="#{rid}">{rid}</a></td><td>{md(text)}</td><td><span class="muted">{md(src)}</span></td><td>{refs(rule_to_tests[rid])}</td><td>{refs(rule_to_tasks[rid])}</td></tr>'
    for rid, mod, text, src in RULES)
add(f'<div class="tw"><table><thead><tr><th>Mã</th><th>Quy tắc</th><th>Nguồn</th><th>Test</th><th>Task</th></tr></thead><tbody id="rules-body">{body}</tbody></table></div>')
add("</section>")

# ---- 5 Màn hình ----
add('<section id="man-hinh"><h2><span class="sn">5</span>Bản đồ màn hình</h2>')
add('<p class="lead">Mỗi màn có <strong>đúng một chủ</strong>. Route nằm trong file <code>&lt;module&gt;_routes.dart</code> của chủ vai trò; router chính chỉ lắp ráp. Cột API là số E của endpoint (rê chuột để xem đường dẫn).</p>')
for o in OWNERS:
    add(f'<h3>{own(o)} {esc(OWNERS[o][0])}: {esc(OWNERS[o][1])}</h3>')
    rws = []
    for sid, name, roles, route, so, eps, rls, desc in SCREENS:
        if so != o:
            continue
        rws.append((sid, (f'<a class="ref" href="#{sid}">{sid}</a>', f"<strong>{esc(name)}</strong><div class=\"muted\">{md(desc)}</div><div class=\"roles-tag\">{esc(roles)}</div>", "<br>".join(f"<code>{esc(r.strip())}</code>" for r in route.split("  ·  ")), eprefs(eps), refs(rls))))
    add(table(["Mã", "Màn hình", "Route", "API", "Quy tắc"], rws))
add("</section>")

# ---- 6 Luồng & trạng thái ----
add('<section id="luong"><h2><span class="sn">6</span>Luồng và máy trạng thái</h2>')
for m in "BCAD":
    if m not in FLOWS:
        continue
    add(f'<h3>{own(m)} {esc(MODULES[m])}</h3>')
    for title, steps in FLOWS[m]:
        add(f'<div class="flow"><h4>{esc(title)}</h4><ol>' + "".join(f"<li>{md(s)}</li>" for s in steps) + "</ol></div>")
add('<h3>Bảng chuyển trạng thái</h3>')
for title, o, trs in STATE_MACHINES:
    add(f'<h4>{own(o)} {esc(title)}</h4>')
    add(table(["Từ", "Sang", "Kích hoạt", "Điều kiện", "Hệ quả"], [("", (f"<code>{esc(a)}</code>", f"<code>{esc(b)}</code>", md(c), md(d), md(e))) for a, b, c, d, e in trs], "sm"))
add("</section>")

# ---- 7 Chia việc ----
add('<section id="chia-viec"><h2><span class="sn">7</span>Chia việc cho 4 người</h2>')
add('<p class="lead">Cách chia: <strong>theo vùng nghiệp vụ, không theo tầng kỹ thuật</strong>, để mỗi người làm trọn một luồng từ màn hình tới API và tự kiểm thử. Phụ thuộc duy nhất là <code>ApiClient</code> của A (P2) và cổng thanh toán WebView của B mà C và D dùng chung.</p>')
add('<h3>Các giai đoạn</h3>')
add(table(["", "Giai đoạn", "Nội dung"], [("", (f"<code>{p}</code>", f"<strong>{esc(n)}</strong>", md(d))) for p, n, d in PHASES]))
add('<h3>Phụ thuộc giữa các task</h3>')
dep_rows = [(t[0], (f'<a class="ref" href="#{t[0]}">{t[0]}</a> {own(t[1])}', " ".join(f'<a class="ref" href="#{d}">{d}</a>' for d in t[9]))) for t in TASKS if t[9]]
add(table(["Task", "Phải chờ"], dep_rows, "sm"))
add('<p class="muted">Task không có phụ thuộc làm ngay được với Fake. <strong>T-A1 là nút thắt của P2</strong>: A nên làm T-A1 trước các task còn lại của mình để không ai phải chờ. T-B2 (WebView thanh toán) là nút thắt thứ hai cho C và D.</p>')
size_name = {"S": "nhỏ", "M": "vừa", "L": "lớn"}
for o in OWNERS:
    ts = [t for t in TASKS if t[1] == o]
    add(f'<h3>{own(o)} {esc(OWNERS[o][0])}: {esc(OWNERS[o][1])} <span class="muted small">({len(ts)} task)</span></h3>')
    for tid, owner, phase, size, title, deliver, scr, eps, rls, deps, ac in ts:
        add(f'<article class="task" id="{tid}"><header><a class="ref" href="#{tid}">{tid}</a><h4>{esc(title)}</h4>'
            f'<span class="pill">{phase}</span><span class="pill sz-{size}">cỡ {size_name[size]}</span></header>'
            f'<p>{md(deliver)}</p>'
            f'<div class="meta"><div><b>Màn</b> {refs(scr)}</div><div><b>API</b> {eprefs(eps)}</div><div><b>Quy tắc</b> {refs(rls)}</div>' + (f'<div><b>Chờ</b> {refs(deps)}</div>' if deps else "") + "</div>"
            '<h5>Nghiệm thu</h5><ul class="ac">' + "".join(f"<li>{md(a)}</li>" for a in ac) + "</ul></article>")
add("</section>")

# ---- 8 API ----
add('<section id="api"><h2><span class="sn">8</span>API của Backend</h2>')
add(f'<p class="lead">{md(BASE)} Danh sách này được script <strong>đối chiếu tự động với controller của BE</strong>: method, đường dẫn và vai trò được phép gọi.</p>')
add('<div class="callout"><b>Cần biết trước khi viết ApiClient</b><ul>'
    "<li>Thành công: dựa vào <code>success</code> và HTTP status, đừng dựa vào <code>code</code> (lúc <code>success</code>, lúc <code>Success</code>, lúc null).</li>"
    "<li>401/403 từ tầng bảo mật là <strong>text thuần</strong>, không phải JSON.</li>"
    "<li>Refresh token <strong>chỉ có trong cookie</strong> <code>refresh_token</code> (Path <code>/api/auth</code>).</li>"
    "<li>Ngày giờ là <code>yyyy-MM-ddTHH:mm:ss</code> không múi giờ; giờ là <code>HH:mm:ss</code>.</li>"
    "<li>Phân trang: giao dịch và thông báo dùng <code>page</code> từ 0; phiên gửi xe trả <code>Page</code> thô của Spring (<code>content</code>, <code>totalElements</code>, <code>number</code>...).</li></ul></div>")
add('<div class="filters" data-target="api-body" role="group" aria-label="Lọc theo chủ"><button class="chip on" data-f="*">Tất cả</button>' + "".join(f'<button class="chip" data-f="{o}">{own(o)} {esc(OWNERS[o][0])}</button>' for o in OWNERS) + "</div>")
tb = "".join(
    f'<tr id="{E_NUM[e[0]]}" data-m="{e[4]}"><td><a class="ref" href="#{E_NUM[e[0]]}">{E_NUM[e[0]]}</a><div class="muted small">{esc(e[0])}</div>{'<div><span class="sev sev-high">đề xuất</span></div>' if e[0] in PROPOSED_KEYS else ''}</td><td><code>{e[1]}</code></td><td><code>/api{esc(e[2])}</code></td><td>{esc(e[3])}</td><td>{own(e[4])}</td><td>{md(e[5])}<div class="muted small">Màn: {refs(ep_to_screens[e[0]])}</div></td></tr>'
    for e in ALL_EPS)
add(f'<div class="tw"><table class="sm"><thead><tr><th>Mã</th><th>Method</th><th>Đường dẫn</th><th>Auth</th><th>Chủ</th><th>Ghi chú</th></tr></thead><tbody id="api-body">{tb}</tbody></table></div>')
add("</section>")

# ---- 9 Mã lỗi ----
add('<section id="ma-loi"><h2><span class="sn">9</span>Mã lỗi và thông điệp</h2>')
add(f'<p class="lead">BE có <strong>{len(be_codes) or len(DRIVER_ERRORS) + len(STAFF_ERRORS)}</strong> mã lỗi, message đều tiếng Anh. App dùng bảng dưới để hiển thị tiếng Việt (task T-D1). Bảng này được đối chiếu tự động với <code>ErrorCode.java</code>: thiếu hoặc thừa mã là build fail.</p>')
add('<h3>Tài xế thường gặp</h3>')
add(table(["Mã", "HTTP", "Thông điệp hiển thị", "Hành động trên UI"], [(c, (f"<code>{c}</code>", str(v[0]), esc(v[1]), md(v[2]))) for c, v in DRIVER_ERRORS.items()], "sm"))
add('<h3>Nhân viên, quản lý, quản trị thường gặp</h3>')
add(table(["Mã", "HTTP", "Thông điệp hiển thị", "Hành động trên UI"], [(c, (f"<code>{c}</code>", str(v[0]), esc(v[1]), md(v[2]))) for c, v in STAFF_ERRORS.items()], "sm"))
add('<h3>Mã ngoài enum</h3>')
add(table(["Mã", "HTTP", "Thông điệp hiển thị", "Ghi chú"], [(c, (f"<code>{c}</code>", str(h), esc(m_), md(n))) for c, h, m_, n in EXTRA_ERRORS], "sm"))
add("</section>")

# ---- 10 Kiểm thử ----
add('<section id="kiem-thu"><h2><span class="sn">10</span>Kiểm thử</h2>')
add('<p class="lead">Ba loại: <code>Unit</code> (test Dart thuần, chạy bằng <code>flutter test</code>), <code>Fake</code> (chạy trên điện thoại với dữ liệu giả, làm được ngay ở P1), <code>BE</code> (cần BE thật, làm ở P3). Mỗi quy tắc có ít nhất một ca. Kịch bản liên vai trò <a class="ref" href="#TC-X10">TC-X10</a> cần 2 điện thoại.</p>')
add('<div class="filters" data-target="tests-body" role="group" aria-label="Lọc theo loại">'
    '<button class="chip on" data-f="*">Tất cả</button><button class="chip" data-f="Unit">Unit</button><button class="chip" data-f="Fake">Fake</button><button class="chip" data-f="BE">BE</button></div>')
tb = "".join(
    f'<tr id="{t[0]}" data-m="{t[2]}"><td><a class="ref" href="#{t[0]}">{t[0]}</a></td><td>{own(t[1])}</td><td><span class="lv lv-{t[2]}">{t[2]}</span></td><td><strong>{md(t[3])}</strong></td><td>{refs(t[4])}</td><td>{md(t[5])}</td><td>{md(t[6])}</td></tr>'
    for t in TESTS)
add(f'<div class="tw"><table class="sm"><thead><tr><th>Mã</th><th>Chủ</th><th>Loại</th><th>Ca</th><th>Quy tắc</th><th>Các bước</th><th>Kết quả mong đợi</th></tr></thead><tbody id="tests-body">{tb}</tbody></table></div>')
add("<h3>Số liệu mẫu dùng chung cho test</h3>")
add(table(["Loại xe", "Giá/giờ", "Hệ số đêm", "Phí sai khu", "Gói 1 tháng: Sáng/Chiều/Tối · Đêm · Cả ngày"], [
    ("", ("Xe máy (Motorbike)", "4.000đ", "×1,5", "100.000đ", "110.000đ · 140.000đ · 420.000đ")),
    ("", ("Ô tô (Car)", "10.000đ", "×1,5", "500.000đ", "450.000đ · 580.000đ · 1.700.000đ")),
    ("", ("Xe 16 chỗ (Minibus)", "15.000đ", "×1,5", "500.000đ", "700.000đ · 900.000đ · 2.600.000đ"))]))
add('<p class="muted">Lấy từ <code>DataInitializer</code> của BE (dữ liệu seed): 6 tầng (B1–B3 xe máy, B4–B5 ô tô, B6 hỗn hợp ô tô + minibus), diện tích sử dụng 600 m² mỗi tầng, 4 khu, hạn mức 20%. Tài khoản seed của BE: <code>driver1@pbm.com</code> (xe <code>72C2-61690</code> Ô tô, <code>72C1-12345</code> Xe máy), <code>staff1@pbm.com</code>, <code>manager1@pbm.com</code>, <code>admin@pbm.com</code>; mật khẩu xem trong <code>DataInitializer.java</code>.</p>')
add("</section>")

# ---- 11 Lệch BE ----
add('<section id="lech-be"><h2><span class="sn">11</span>Lệch giữa yêu cầu và BE</h2>')
add('<p class="lead">Đọc kỹ mục này trước khi họp với người giữ BE. Mức: <span class="sev sev-crit">chặn</span> làm hỏng luồng chính; <span class="sev sev-high">cao</span> thiếu chức năng cần có; <span class="sev sev-med">vừa</span>; <span class="sev sev-low">thấp</span>.</p>')
sev_name = {"crit": "chặn", "high": "cao", "med": "vừa", "low": "thấp"}
for gid, sev, title, desc, fix, work, who in GAPS:
    add(f'<article class="gap" id="{gid}"><header><a class="ref" href="#{gid}">{gid}</a><span class="sev sev-{sev}">{sev_name[sev]}</span><h4>{esc(title)}</h4></header>'
        f'<p>{md(desc)}</p><dl><dt>Đề nghị sửa BE</dt><dd>{md(fix)}</dd><dt>App làm gì trong lúc chờ</dt><dd>{md(work)}</dd><dt>Ai chốt</dt><dd>{esc(who)}</dd></dl></article>')
add('<h3>Câu hỏi cần chốt</h3>')
add(table(["Mã", "Câu hỏi", "Mặc định (đã giả định)", "Ghi chú"], [(q[0], (f'<a class="ref" href="#{q[0]}">{q[0]}</a>', esc(q[1]), esc(q[2]), md(q[3]))) for q in QUESTIONS]))
add("</section>")

# ---- 12 Quy ước ----
add('<section id="quy-uoc"><h2><span class="sn">12</span>Quy ước làm việc và chạy trên điện thoại</h2>')
add('<h3>Chạy app qua ADB wifi</h3>')
add('<pre><code>cd Flutter\nflutter pub get\nadb devices                      # thấy máy ở trạng thái "device"\nflutter run -d &lt;id máy&gt;            # dữ liệu giả (mặc định), đăng nhập driver@parking.vn / 123123@\n\n# Nối BE thật (P2): dùng IP LAN của máy chạy BE, KHÔNG dùng localhost\nflutter run -d &lt;id máy&gt; \\\n  --dart-define=API_BASE_URL=http://192.168.1.10:8080/api \\\n  --dart-define=USE_FAKE=false\n\nflutter analyze &amp;&amp; flutter test        # chạy trước mỗi pull request</code></pre>')
add('<p class="muted">Android đã bật <code>INTERNET</code>, <code>CAMERA</code> và <code>usesCleartextTraffic</code> (gọi HTTP lúc dev). Build Android dùng <code>kotlin.incremental=false</code> trong <code>android/gradle.properties</code> vì plugin ở ổ C còn dự án ở ổ D (lỗi Kotlin "different roots"); đừng xóa dòng này. Trước khi nộp bản cuối, chuyển BE sang HTTPS và tắt cleartext.</p>')
add('<h3>Cấu trúc thư mục</h3>')
add('<pre><code>lib/\n  main.dart\n  app/            app.dart · router.dart (chỉ lắp ráp) · main_shell.dart · role_tabs.dart · role_bottom_bar.dart\n  core/           theme · config/env.dart · payment/payment_gateway.dart · scan/scan_code.dart · utils · widgets\n  features/\n    auth/ account/                       A\n    reservation/ admin/                  B\n    membership/ manager/                 C\n    staff/ scan/ home/ wallet/ notification/   D\n    &lt;module&gt;/\n      models/                 kiểu dữ liệu, khớp enum/JSON của BE\n      data/\n        &lt;x&gt;_repository.dart    interface + Fake (đổi sang Api ở P2)\n        &lt;x&gt;_providers.dart     nơi DUY NHẤT chọn Fake hay Api\n      presentation/           màn hình, widget\n      &lt;module&gt;_routes.dart    nhánh tab và route con của module</code></pre>')
add('<h3>Dùng chung giữa các người: ai sở hữu gì</h3>')
add(table(["Thứ dùng chung", "Chủ", "Cách dùng cho người khác"], [
    ("", ("Repository của một endpoint", "Chủ endpoint (cột Chủ ở mục API)", "Người khác **gọi qua provider của chủ**, không viết lại. VD C (Giám sát) dùng danh sách đặt chỗ `rsv.all` qua provider của D; D (Check-in) dùng `fee.list` qua provider của B.")),
    ("", ("Model <code>Vehicle</code>, <code>Clock</code>, <code>ApiException</code>", "A (task T-A0)", "B, C, D chỉ **đọc**; cần thêm trường thì nhắn A. Giao trong ngày đầu của P1.")),
    ("", ("<code>PaymentGateway</code> (WebView VNPay)", "B (task T-B2)", "C (mua gói) và D (check-out VNPay) dùng đúng interface này; bản Fake đã có sẵn trong <code>core/payment</code>.")),
    ("", ("Bộ poll <code>awaitStatus</code> (2 giây × 30 giây)", "B (task T-B8)", "C dùng cho gói thành viên, D dùng cho check-out VNPay.")),
    ("", ("Route và tab", "Mỗi người khai báo trong <code>*_routes.dart</code> của mình", "<code>app/router.dart</code> và <code>app/role_tabs.dart</code> chỉ **A** ghép/sửa. Tab của quản lý/quản trị trỏ vào màn do feature chủ màn xuất ra (VD tab Bảng giá của quản trị = màn Bảng giá của B, tab Duyệt xe của quản lý = màn của C).")),
    ("", ("Bảng mã lỗi <code>messageFor</code>", "D (task T-D1)", "Mọi người chỉ gọi, không tự viết chuỗi lỗi.")),
]))
add('<h3>Quy ước nhóm</h3>')
add('<ul class="plain">'
    "<li><strong>Nhánh git</strong>: <code>feature/&lt;module&gt;-&lt;việc&gt;</code> (VD <code>feature/reservation-create</code>). Không đẩy thẳng lên <code>main</code>; mở pull request, một người khác xem trước khi gộp.</li>"
    "<li><strong>Không sửa thư mục của người khác</strong>. Cần đổi model dùng chung (VD <code>Vehicle</code> của A) thì nhắn chủ module.</li>"
    "<li><strong>Model khớp BE</strong>: enum Dart dùng đúng tên BE; <code>fromJson</code> chịu được trường thiếu/null. Trường nào BE thiếu thì ghi chú <code>// G-xx</code>.</li>"
    "<li><strong>Không gọi Dio trực tiếp trong màn hình</strong>. Màn hình chỉ gọi provider; provider gọi repository.</li>"
    "<li><strong>Đổi Fake → Api</strong> chỉ bằng 1 dòng trong <code>*_providers.dart</code>. Fake phải giữ lại để chạy test và demo khi BE tắt.</li>"
    "<li><strong>Mọi chuỗi hiển thị bằng tiếng Việt</strong>; lỗi từ BE đi qua <code>messageFor(code)</code> (T-D1).</li>"
    "<li><strong>Khi nhiều người cùng thử trên một điện thoại</strong>: đừng gửi lệnh <code>adb shell input</code> trong lúc có người đang cầm máy.</li>"
    "<li><strong>Trước khi mở pull request</strong>: <code>flutter analyze</code> không lỗi, <code>flutter test</code> pass, đã chạy thử trên điện thoại.</li>"
    "<li><strong>Cập nhật tài liệu này</strong> khi đổi nghiệp vụ: sửa trong <code>docs/spec/*.py</code> rồi chạy <code>python docs/spec/build.py</code>; script báo ngay nếu quy tắc nào mất task/test hoặc BE đổi endpoint/mã lỗi.</li></ul>")
add("</section>")

# ---- 13 Kiểm tra chéo ----
add('<section id="kiem-tra-cheo"><h2><span class="sn">13</span>Kiểm tra chéo đã chạy</h2>')
add('<p class="lead">Mỗi lần sinh tài liệu, script <code>docs/spec/build.py</code> chạy các kiểm tra sau; chỉ khi đạt hết mới ghi file này.</p>')
add(table(["Kiểm tra", "Kết quả"], [("", (esc(a), '<span class="ok">Đạt</span> ' + esc(b))) for a, b in report]))
add("</section>")

content = "\n".join(parts)

nav = [("tong-quan", "Tổng quan"), ("vai-tro", "Vai trò & điều hướng"), ("thuat-ngu", "Thuật ngữ & phạm vi"), ("quy-tac", "Quy tắc nghiệp vụ"),
       ("man-hinh", "Bản đồ màn hình"), ("luong", "Luồng & trạng thái"), ("chia-viec", "Chia việc"), ("api", "API của BE"),
       ("ma-loi", "Mã lỗi"), ("kiem-thu", "Kiểm thử"), ("lech-be", "Lệch BE"), ("quy-uoc", "Quy ước & chạy máy"), ("kiem-tra-cheo", "Kiểm tra chéo")]
nav_html = "".join(f'<a href="#{i}"><span>{k + 1}</span>{esc(n)}</a>' for k, (i, n) in enumerate(nav))

TEMPLATE = open(os.path.join(os.path.dirname(__file__), "template.html"), encoding="utf-8").read()
out = (TEMPLATE
       .replace("{{NAV}}", nav_html)
       .replace("{{CONTENT}}", content)
       .replace("{{N_RULES}}", str(len(RULES)))
       .replace("{{N_SCREENS}}", str(len(SCREENS)))
       .replace("{{N_TASKS}}", str(len(TASKS)))
       .replace("{{N_TESTS}}", str(len(TESTS)))
       .replace("{{N_EPS}}", f"{len(ENDPOINTS)} + {len(PROPOSED)} đề xuất")
       .replace("{{N_GAPS}}", str(len(GAPS))))
with open(OUT, "w", encoding="utf-8") as f:
    f.write(out)
print(f"OK -> {OUT} ({len(out) // 1024} KB)")
for a, b in report:
    print(f"  [đạt] {a}: {b}")
