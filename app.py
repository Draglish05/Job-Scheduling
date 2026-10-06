"""
app.py - Giao diện web (Streamlit) cho ứng dụng xếp lịch.

Chạy:  streamlit run app.py

Cách Streamlit hoạt động (quan trọng): mỗi lần bạn bấm một nút hay đổi một ô,
Streamlit chạy lại TOÀN BỘ file này từ trên xuống dưới. Vì vậy dữ liệu cần nhớ
(ví dụ ai đang đăng nhập) phải để trong st.session_state, còn dữ liệu lâu dài thì
để trong database.
"""
import io
import os
import time
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

import auth
import database as db
import solver as sv

DB_PATH = os.environ.get("CUA_HANG_DB", "cua_hang.db")

# ---- Độ trễ (giây): chỉnh các số này nếu muốn nhanh hơn hoặc chậm hơn ----
TRE_DANG_NHAP = 1.0      # màn hình "Đang đăng nhập..."
TRE_DANG_XUAT = 0.8      # màn hình "Đang đăng xuất..."
TRE_DOI_TRANG = 0.3      # chờ ngắn khi chuyển trang
THOI_GIAN_THONG_BAO = 3  # thông báo nhỏ hiện bao lâu (giây)

# Hiệu ứng chuyển động (chỉ dùng CSS). Muốn tắt hết: đặt HIEU_UNG = False
HIEU_UNG = True
CSS_HIEU_UNG = """
<style>
:root { --luot: cubic-bezier(0.22, 1, 0.36, 1); }   /* đường cong lướt êm, vào nhanh rồi giảm tốc */

@keyframes luot_len   { from {opacity: 0; transform: translateY(18px);}  to {opacity: 1; transform: none;} }
@keyframes luot_phai  { from {opacity: 0; transform: translateX(-28px);} to {opacity: 1; transform: none;} }
@keyframes luot_trai  { from {opacity: 0; transform: translateX(28px);}  to {opacity: 1; transform: none;} }
@keyframes hien_ra    { from {opacity: 0; transform: scale(0.96);}       to {opacity: 1; transform: none;} }

/* Thanh bên trượt vào từ trái */
[data-testid="stSidebarContent"] { animation: luot_phai 0.6s var(--luot) both; }

/* Tiêu đề trang lướt xuống nhẹ, từng khối nội dung lướt lên lần lượt */
[data-testid="stMainBlockContainer"] h1, [data-testid="stMainBlockContainer"] h2 { animation: luot_phai 0.55s var(--luot) both; }
[data-testid="stMainBlockContainer"] [data-testid="stElementContainer"] { animation: luot_len 0.6s var(--luot) both; }
[data-testid="stMainBlockContainer"] [data-testid="stElementContainer"]:nth-child(1) { animation-delay: 0.00s; }
[data-testid="stMainBlockContainer"] [data-testid="stElementContainer"]:nth-child(2) { animation-delay: 0.06s; }
[data-testid="stMainBlockContainer"] [data-testid="stElementContainer"]:nth-child(3) { animation-delay: 0.12s; }
[data-testid="stMainBlockContainer"] [data-testid="stElementContainer"]:nth-child(4) { animation-delay: 0.18s; }
[data-testid="stMainBlockContainer"] [data-testid="stElementContainer"]:nth-child(5) { animation-delay: 0.24s; }
[data-testid="stMainBlockContainer"] [data-testid="stElementContainer"]:nth-child(6) { animation-delay: 0.30s; }
[data-testid="stMainBlockContainer"] [data-testid="stElementContainer"]:nth-child(n+7) { animation-delay: 0.36s; }

/* Khung đăng nhập hiện ra dạng phóng nhẹ */
[data-testid="stVerticalBlockBorderWrapper"] { animation: hien_ra 0.6s var(--luot) both; }

/* Thông báo nhỏ trượt vào từ phải */
[data-testid="stToast"], [data-testid="stToastContainer"] > div { animation: luot_trai 0.45s var(--luot) both; }

/* Cảnh báo / thành công / lỗi */
[data-testid="stAlert"] { animation: luot_phai 0.5s var(--luot) both; }

/* Nút bấm: nổi lên khi rê chuột, nhún xuống khi bấm */
button { transition: transform 0.25s var(--luot), box-shadow 0.25s var(--luot), background-color 0.25s, border-color 0.25s, opacity 0.25s !important; }
button:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(0, 0, 0, 0.28); }
button:active:not(:disabled) { transform: translateY(0) scale(0.97); box-shadow: none; }

/* Mục chọn trang ở thanh bên: dịch nhẹ sang phải khi rê chuột */
[data-testid="stSidebar"] [role="radiogroup"] label { transition: transform 0.25s var(--luot), background-color 0.25s; border-radius: 8px; }
[data-testid="stSidebar"] [role="radiogroup"] label:hover { transform: translateX(6px); }

/* Ô nhập, ô chọn, bảng: viền và bóng chuyển mượt */
input, textarea, [data-baseweb="select"] > div, [data-testid="stDataFrame"], [data-testid="stExpander"] {
    transition: border-color 0.3s var(--luot), box-shadow 0.3s var(--luot);
}
[data-testid="stExpander"] details[open] > div { animation: luot_len 0.4s var(--luot) both; }
.stTabs [data-baseweb="tab-panel"] { animation: luot_len 0.45s var(--luot) both; }

/* Người dùng bật "giảm chuyển động" trong hệ điều hành thì tắt hết */
@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
</style>
"""
if HIEU_UNG:
    st.markdown(CSS_HIEU_UNG, unsafe_allow_html=True)


def bao(noi_dung, bieu_tuong="✅", chay_lai=False):
    """
    Thông báo nhỏ nổi lên góc màn hình, tự tắt sau vài giây.
    chay_lai=True: hiện thông báo SAU khi trang chạy lại (dùng khi ngay sau đó phải st.rerun(),
    nếu không thông báo sẽ biến mất trước khi kịp đọc).
    """
    if chay_lai:
        st.session_state.setdefault("hang_cho_thong_bao", []).append((noi_dung, bieu_tuong))
        st.rerun()
    else:
        st.toast(noi_dung, icon=bieu_tuong, duration=THOI_GIAN_THONG_BAO)


def hien_thong_bao_dang_cho():
    for noi_dung, bieu_tuong in st.session_state.pop("hang_cho_thong_bao", []):
        st.toast(noi_dung, icon=bieu_tuong, duration=THOI_GIAN_THONG_BAO)

st.set_page_config(page_title="Xếp lịch làm", page_icon="🗓️", layout="wide")


# ---------------------------------------------------------------
# Hàm phụ
# ---------------------------------------------------------------
def thu_hai(d):
    return d - timedelta(days=d.weekday())


def nhan_ca(cfg_ca, gio):
    """Tên ca kèm giờ để hiển thị, ví dụ 'Sáng (07:00-12:00)'."""
    g = gio.get(cfg_ca)
    return f"{cfg_ca} ({g['bat_dau']}-{g['ket_thuc']})" if g and g["bat_dau"] else cfg_ca


def luoi_tick(ngay, ca, o_chon):
    """Bảng tick: hàng = ca, cột = ngày, ô = True nếu đã chọn."""
    return pd.DataFrame([[(n, c) in o_chon for n in ngay] for c in ca], index=ca, columns=ngay)


def o_tu_luoi(df):
    return {(n, c) for c in df.index for n in df.columns if bool(df.loc[c, n])}


def bang_lich(lich_ca, ngay, ca):
    """lich_ca = {(ngày, ca): [tên]} -> bảng chữ để hiển thị."""
    return pd.DataFrame([[", ".join(lich_ca.get((n, c), [])) for n in ngay] for c in ca],
                        index=ca, columns=ngay)


def ma_tran_lich(lich_ca, nhan_vien, ngay, ca):
    return [[[1 if nv in lich_ca.get((n, c), []) else 0 for c in ca] for n in ngay] for nv in nhan_vien]


def xuat_excel(df_lich, df_thong_ke):
    bo_nho = io.BytesIO()
    with pd.ExcelWriter(bo_nho, engine="openpyxl") as w:
        df_lich.to_excel(w, sheet_name="Lịch tuần")
        df_thong_ke.to_excel(w, sheet_name="Thống kê", index=False)
    return bo_nho.getvalue()


def df_thong_ke(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.rename(columns={"ten": "Nhân viên", "loai": "Loại", "so_ca": "Số ca", "so_gio": "Số giờ",
                              "so_ca_kho": "Ca khó", "so_ngay": "Số ngày"})


# ---------------------------------------------------------------
# Đăng nhập
# ---------------------------------------------------------------
def trang_dang_nhap(conn):
    # 3 cột tỉ lệ 3:2:3, chỉ dùng cột giữa => khung hẹp nằm giữa trang (muốn hẹp hơn thì tăng số hai bên)
    _, giua, _ = st.columns([3, 2, 3])
    with giua:
        st.write("")
        st.write("")
        with st.container(border=True):
            st.markdown("<h3 style='text-align:center'>🗓️ Xếp lịch làm</h3>", unsafe_allow_html=True)
            co_admin = conn.execute("SELECT 1 FROM tai_khoan WHERE vai_tro='admin'").fetchone() is not None
            if not co_admin:
                st.info("Lần đầu dùng: hãy tạo tài khoản admin (chủ cửa hàng).")
                with st.form("tao_admin", border=False):
                    ten = st.text_input("Tên đăng nhập admin")
                    mk = st.text_input("Mật khẩu (ít nhất 8 ký tự)", type="password")
                    if st.form_submit_button("Tạo admin", width="stretch"):
                        try:
                            auth.tao_admin_dau_tien(conn, ten, mk)
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))
                return
            with st.form("dang_nhap", border=False):
                ten = st.text_input("Tên đăng nhập")
                mk = st.text_input("Mật khẩu", type="password")
                if st.form_submit_button("Đăng nhập", type="primary", width="stretch"):
                    try:
                        nd = auth.dang_nhap(conn, ten, mk)
                    except auth.TaiKhoanBiKhoa as e:
                        st.error(str(e))
                        return
                    if nd is None:
                        st.error("Sai tên đăng nhập hoặc mật khẩu.")
                    else:
                        with st.spinner("Đang đăng nhập..."):
                            time.sleep(TRE_DANG_NHAP)
                        st.session_state["nguoi_dung"] = nd
                        st.rerun()


# ---------------------------------------------------------------
# Các trang
# ---------------------------------------------------------------
def tai_cau_hinh(conn, tuan):
    cfg = db.doc_cau_hinh(conn, tuan)
    # Khi không có ai full-time, database trả về None; đổi thành danh sách rỗng để dùng `in` được
    if not cfg["full_time"]:
        cfg["full_time"] = []
    gio = db.doc_gio_ca(conn)
    return cfg, gio


def trang_dang_ky(conn, nd, tuan):
    st.header("Đăng ký ca làm")
    cfg, gio = tai_cau_hinh(conn, tuan)
    if nd["vai_tro"] == "admin":
        ten = st.selectbox("Đăng ký thay cho", cfg["nhan_vien"])
    else:
        ten = conn.execute("SELECT ten FROM nhan_vien WHERE id=?", (nd["nhan_vien_id"],)).fetchone()[0]
        st.write(f"Nhân viên: **{ten}**")
    if not auth.co_the_sua_dang_ky(conn, nd, ten):
        st.error("Bạn không có quyền sửa đăng ký này.")
        return
    if ten in cfg["full_time"]:
        st.info("Bạn là nhân viên full-time: lịch do admin xếp cố định, không cần đăng ký.")
        return
    st.caption("Tick vào những ca bạn LÀM ĐƯỢC trong tuần này. Để trống là không làm được.")
    hien_tai = db.doc_dang_ky(conn, tuan).get(ten, set())
    luoi = luoi_tick(cfg["ngay"], cfg["ca"], hien_tai)
    luoi.index = [nhan_ca(c, gio) for c in cfg["ca"]]
    sua = st.data_editor(luoi, key=f"dk_{tuan}_{ten}", width="stretch")
    if st.button("Lưu đăng ký", type="primary"):
        sua.index = cfg["ca"]
        db.luu_dang_ky(conn, tuan, ten, o_tu_luoi(sua))
        bao("Đã lưu đăng ký.")
    if nd["vai_tro"] == "admin":
        if st.button("Chép đăng ký từ tuần trước"):
            truoc = (datetime.strptime(tuan, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
            db.sao_chep_dang_ky(conn, truoc, tuan)
            bao("Đã chép đăng ký từ tuần trước.", chay_lai=True)


def hien_lich(conn, tuan, cfg, gio, nd):
    lich_ca = db.doc_lich(conn, tuan)
    if not any(lich_ca.values()):
        st.info("Tuần này chưa có lịch.")
        return lich_ca
    bang = bang_lich(lich_ca, cfg["ngay"], cfg["ca"])
    bang.index = [nhan_ca(c, gio) for c in cfg["ca"]]
    st.dataframe(bang, width="stretch")
    if nd["vai_tro"] == "nhan_vien":
        ten = conn.execute("SELECT ten FROM nhan_vien WHERE id=?", (nd["nhan_vien_id"],)).fetchone()[0]
        cua_minh = [f"{n} - {c}" for (n, c), ds in lich_ca.items() if ten in ds]
        st.subheader("Ca của bạn")
        st.write("; ".join(cua_minh) if cua_minh else "Tuần này bạn không có ca.")
    return lich_ca


def trang_lich(conn, nd, tuan):
    st.header("Lịch tuần")
    cfg, gio = tai_cau_hinh(conn, tuan)
    if nd["vai_tro"] == "admin":
        nut_xep(conn, tuan, cfg)
    lich_ca = hien_lich(conn, tuan, cfg, gio, nd)
    if nd["vai_tro"] != "admin" or not any(lich_ca.values()):
        return
    # Kiểm tra luật cứng cho lịch đang lưu (kể cả sau khi sửa tay)
    loi = sv.kiem_tra_lich(ma_tran_lich(lich_ca, cfg["nhan_vien"], cfg["ngay"], cfg["ca"]),
                           cfg["nhan_vien"], cfg["ngay"], cfg["ca"], cfg["so_nguoi"],
                           lam_duoc=cfg["lam_duoc"], so_nguoi_rieng=cfg["so_nguoi_rieng"],
                           toi_da_tuan=cfg["toi_da_tuan"], cap_ca_cam=cfg["cap_ca_cam"],
                           ghim=cfg["ghim"], khong_xep=cfg["khong_xep"], full_time=cfg["full_time"])
    if loi:
        st.warning("Lịch đang có chỗ vi phạm luật:")
        for l in loi:
            st.write("- " + str(l))
    else:
        st.success("Lịch hợp lệ, không vi phạm luật cứng nào.")
    with st.expander("Sửa tay một ô"):
        c1, c2, c3, c4 = st.columns(4)
        ten = c1.selectbox("Nhân viên", cfg["nhan_vien"], key="st_nv")
        ngay = c2.selectbox("Ngày", cfg["ngay"], key="st_ngay")
        ca = c3.selectbox("Ca", cfg["ca"], key="st_ca")
        hd = c4.radio("Việc", ["Thêm vào ca", "Bỏ khỏi ca"], key="st_hd")
        if st.button("Áp dụng"):
            db.sua_lich_tay(conn, tuan, ten, ngay, ca, hd == "Thêm vào ca")
            bao("Đã cập nhật ô lịch.", chay_lai=True)
    bang = bang_lich(lich_ca, cfg["ngay"], cfg["ca"])
    st.download_button("⬇️ Xuất Excel", xuat_excel(bang, df_thong_ke(db.thong_ke_tuan(conn, tuan))),
                       file_name=f"lich_{tuan}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def nut_xep(conn, tuan, cfg):
    st.caption("Máy xếp theo đăng ký của tuần này, các ca đã ghim và lịch sử các tuần trước.")
    cho_phep = st.session_state.get("cho_phep_noi_long") == tuan
    if st.button("⚙️ Xếp lịch tự động", type="primary") or cho_phep:
        with st.spinner("Đang tính toán..."):
            kq = sv.xep_lich_tu_van(hoi=lambda van_de: cho_phep, **cfg)
        r = kq["ket_qua"]
        if r["lich"] is None:
            st.error("Không xếp được lịch. Các vấn đề tìm thấy:")
            for v in kq["van_de"]:
                st.write("- " + v["noi_dung"])
            if kq["van_de"] and not cho_phep:
                if st.button("Cho phép một người làm hai ca trong một ngày rồi xếp lại"):
                    st.session_state["cho_phep_noi_long"] = tuan
                    st.rerun()
            return
        db.luu_lich(conn, tuan, sv.lich_theo_ca(r["lich"], cfg["nhan_vien"], cfg["ngay"], cfg["ca"]))
        st.session_state.pop("cho_phep_noi_long", None)
        bao("Đã xếp và lưu lịch.", "🗓️")
        if kq["da_noi_long"]:
            st.warning("Lịch này có người làm hai ca trong một ngày (do bạn đồng ý):")
            for dong in kq["nguoi_lam_hai_ca"]:
                st.write("- " + str(dong))


def trang_ghim(conn, tuan):
    st.header("Ghim ca và lịch full-time")
    cfg, gio = tai_cau_hinh(conn, tuan)
    ten = st.selectbox("Nhân viên", cfg["nhan_vien"])
    la_ft = ten in cfg["full_time"]
    if la_ft:
        st.info("Full-time: lịch của người này là các ô bạn ghim 'Bắt buộc làm' bên dưới.")
    loai = st.radio("Loại ghim", ["Bắt buộc làm", "Không được xếp"], horizontal=True)
    key = "lam" if loai == "Bắt buộc làm" else "nghi"
    ghim, khong = db.doc_ghim(conn, tuan)
    hien_tai = (ghim if key == "lam" else khong).get(ten, set())
    luoi = luoi_tick(cfg["ngay"], cfg["ca"], hien_tai)
    sua = st.data_editor(luoi, key=f"gh_{tuan}_{ten}_{key}", width="stretch")
    if st.button("Lưu ghim", type="primary"):
        try:
            db.dat_ghim(conn, tuan, ten, o_tu_luoi(sua), loai=key)
            bao("Đã lưu ghim.")
        except ValueError as e:
            st.error(str(e))


def trang_thong_ke(conn, nd, tuan):
    st.header("Thống kê")
    che_do = st.radio("Xem theo", ["Tuần đang chọn", "Tháng"], horizontal=True)
    if che_do == "Tuần đang chọn":
        rows = db.thong_ke_tuan(conn, tuan)
    else:
        hom_nay = date.today()
        c1, c2 = st.columns(2)
        nam = c1.number_input("Năm", 2020, 2100, hom_nay.year)
        thang = c2.number_input("Tháng", 1, 12, hom_nay.month)
        rows = db.thong_ke_thang(conn, int(nam), int(thang))
    if nd["vai_tro"] == "nhan_vien":
        ten = conn.execute("SELECT ten FROM nhan_vien WHERE id=?", (nd["nhan_vien_id"],)).fetchone()[0]
        rows = [r for r in rows if r["ten"] == ten]
    st.dataframe(df_thong_ke(rows), width="stretch", hide_index=True)


def trang_nhan_vien(conn):
    st.header("Nhân viên và tài khoản")
    chi_tiet = db.ds_nhan_vien_chi_tiet(conn)
    st.dataframe(pd.DataFrame(chi_tiet).rename(columns={"ten": "Tên", "loai": "Loại", "toi_da_tuan": "Tối đa ca/tuần"}),
                 width="stretch", hide_index=True)
    with st.form("them_nv"):
        st.subheader("Thêm nhân viên")
        c1, c2 = st.columns(2)
        ten = c1.text_input("Tên nhân viên")
        loai = c2.selectbox("Loại", ["part_time", "full_time"])
        tk = c1.text_input("Tên đăng nhập (bỏ trống nếu chưa cần tài khoản)")
        mk = c2.text_input("Mật khẩu ban đầu", type="password")
        if st.form_submit_button("Thêm"):
            if not db.them_nhan_vien(conn, ten, loai=loai):
                st.error("Tên trống hoặc đã tồn tại.")
            else:
                try:
                    if tk:
                        auth.tao_tai_khoan(conn, tk, mk, "nhan_vien", ten.strip())
                    bao(f"Đã thêm {ten.strip()}.", chay_lai=True)   # chạy lại để bảng ở trên hiện ngay
                except ValueError as e:
                    bao(f"Đã thêm nhân viên nhưng chưa tạo được tài khoản: {e}", "⚠️", chay_lai=True)
    ten_ds = [c["ten"] for c in chi_tiet]
    if ten_ds:
        st.subheader("Sửa nhân viên")
        c1, c2, c3 = st.columns(3)
        ten = c1.selectbox("Chọn nhân viên", ten_ds)
        loai = c2.selectbox("Đổi loại thành", ["part_time", "full_time"])
        if c2.button("Đổi loại"):
            db.doi_loai_nhan_vien(conn, ten, loai)
            bao(f"Đã đổi loại của {ten}.", chay_lai=True)
        gh = c3.number_input("Tối đa ca/tuần riêng (0 = dùng mức chung)", 0, 21, 0)
        if c3.button("Lưu giới hạn riêng"):
            db.dat_toi_da_tuan_nhan_vien(conn, ten, int(gh) or None)
            bao(f"Đã lưu giới hạn của {ten}.", chay_lai=True)
        if st.checkbox(f"Tôi chắc chắn muốn xóa {ten} (mất cả đăng ký, lịch sử của người này)"):
            if st.button("Xóa nhân viên"):
                db.xoa_nhan_vien(conn, ten)
                bao(f"Đã xóa {ten}.", "🗑️", chay_lai=True)
    st.subheader("Đặt lại mật khẩu")
    tk_ds = [r[0] for r in conn.execute("SELECT ten_dang_nhap FROM tai_khoan ORDER BY id")]
    with st.form("dat_lai_mk"):
        tk = st.selectbox("Tài khoản", tk_ds)
        mk = st.text_input("Mật khẩu mới", type="password")
        if st.form_submit_button("Đặt lại"):
            try:
                auth.dat_lai_mat_khau(conn, st.session_state["nguoi_dung"], tk, mk)
                bao("Đã đặt lại mật khẩu.")
            except ValueError as e:
                st.error(str(e))


def trang_cai_dat(conn):
    st.header("Cài đặt cửa hàng")
    st.subheader("Các ca")
    st.caption("Mỗi hàng là một ca. Giờ dạng HH:MM. Ca qua nửa đêm: giờ kết thúc nhỏ hơn giờ bắt đầu. "
               "Xóa một ca sẽ xóa đăng ký/lịch của ca đó.")
    gio = db.doc_gio_ca(conn)
    cfg = db.doc_cau_hinh(conn, date.today().strftime("%Y-%m-%d"))
    df = pd.DataFrame([{"Ca": c, "Số người": cfg["so_nguoi"][c], "Bắt đầu": gio[c]["bat_dau"] or "",
                        "Kết thúc": gio[c]["ket_thuc"] or ""} for c in cfg["ca"]])
    sua = st.data_editor(df, num_rows="dynamic", key="ed_ca", width="stretch", hide_index=True)
    st.caption("Muốn xóa một ca: dùng mục \"Xóa bớt ca\" bên dưới (an toàn hơn xóa hàng trong bảng).")
    if st.button("Lưu các ca", type="primary"):
        try:
            ds = []
            for _, r in sua.iterrows():
                if not str(r["Ca"]).strip() or str(r["Ca"]) == "nan":
                    continue
                bd, kt = str(r["Bắt đầu"]).strip(), str(r["Kết thúc"]).strip()
                ds.append((str(r["Ca"]).strip(), int(r["Số người"]), bd, kt) if bd and kt
                          else (str(r["Ca"]).strip(), int(r["Số người"])))
            db.dat_ca(conn, ds)
            bao("Đã lưu các ca.")
        except (ValueError, TypeError) as e:
            st.error(str(e))
    st.subheader("Xóa bớt ca")
    if len(cfg["ca"]) <= 1:
        st.info("Cửa hàng chỉ còn một ca nên không xóa được nữa.")
    else:
        ca_xoa = st.selectbox("Chọn ca muốn xóa", cfg["ca"], key="ca_xoa")
        st.warning(f"Xóa ca **{ca_xoa}** sẽ xóa luôn mọi đăng ký và lịch đã xếp của ca này, không khôi phục được.")
        chac = st.checkbox(f"Tôi chắc chắn muốn xóa ca {ca_xoa}", key=f"chac_xoa_ca_{ca_xoa}")
        if st.button("Xóa ca", disabled=not chac):
            con_lai = []
            for c in cfg["ca"]:
                if c == ca_xoa:
                    continue
                g = gio[c]
                con_lai.append((c, cfg["so_nguoi"][c], g["bat_dau"], g["ket_thuc"]) if g["bat_dau"]
                               else (c, cfg["so_nguoi"][c]))
            db.dat_ca(conn, con_lai)
            bao(f"Đã xóa ca {ca_xoa}.", "🗑️", chay_lai=True)
    st.subheader("Giới hạn ca mỗi tuần")
    hien = db.doc_toi_da_tuan(conn)
    dung = st.checkbox("Dùng giới hạn chung", value=hien is not None)
    so = st.number_input("Tối đa ca/tuần cho mỗi người", 1, 21, hien or 5, disabled=not dung)
    if st.button("Lưu giới hạn"):
        db.dat_toi_da_tuan(conn, int(so) if dung else None)
        bao("Đã lưu giới hạn.")
    st.subheader("Công bằng nhiều tuần")
    n = st.number_input("Xét bao nhiêu tuần trước khi chia đều ca", 0, 26, db.doc_so_tuan_lich_su(conn))
    if st.button("Lưu số tuần"):
        db.dat_so_tuan_lich_su(conn, int(n))
        bao("Đã lưu số tuần.")


def trang_mat_khau(conn, nd):
    st.header("Đổi mật khẩu")
    with st.form("doi_mk"):
        cu = st.text_input("Mật khẩu cũ", type="password")
        moi = st.text_input("Mật khẩu mới (ít nhất 8 ký tự)", type="password")
        if st.form_submit_button("Đổi"):
            try:
                auth.doi_mat_khau(conn, nd, cu, moi)
                bao("Đã đổi mật khẩu.", "🔒")
            except ValueError as e:
                st.error(str(e))


# ---------------------------------------------------------------
# Khung chính
# ---------------------------------------------------------------
def main():
    conn = db.ket_noi(DB_PATH)
    nd = st.session_state.get("nguoi_dung")
    if nd is None:
        trang_dang_nhap(conn)
        return
    hien_thong_bao_dang_cho()

    with st.sidebar:
        st.write(f"Xin chào, **{nd['ten_dang_nhap']}** ({'admin' if nd['vai_tro'] == 'admin' else 'nhân viên'})")
        mac_dinh = thu_hai(date.today()) + timedelta(days=7)
        d = st.date_input("Tuần làm việc (chọn ngày bất kỳ trong tuần)", mac_dinh)
        tuan = thu_hai(d).strftime("%Y-%m-%d")
        st.caption(f"Tuần từ {thu_hai(d):%d/%m/%Y} đến {thu_hai(d) + timedelta(days=6):%d/%m/%Y}")
        if nd["vai_tro"] == "admin":
            trang = st.radio("Trang", ["Lịch tuần", "Đăng ký ca", "Ghim ca / full-time",
                                       "Thống kê", "Nhân viên", "Cài đặt", "Đổi mật khẩu"])
        else:
            trang = st.radio("Trang", ["Đăng ký ca", "Lịch tuần", "Thống kê", "Đổi mật khẩu"])
        if st.button("Đăng xuất"):
            with st.spinner("Đang đăng xuất..."):
                time.sleep(TRE_DANG_XUAT)
            st.session_state.clear()
            st.rerun()

    # Đổi trang: chờ một nhịp ngắn cho chuyển cảnh nhẹ nhàng
    if st.session_state.get("trang_truoc") not in (None, trang):
        with st.spinner("Đang tải..."):
            time.sleep(TRE_DOI_TRANG)
    st.session_state["trang_truoc"] = trang

    if trang == "Lịch tuần":
        trang_lich(conn, nd, tuan)
    elif trang == "Đăng ký ca":
        trang_dang_ky(conn, nd, tuan)
    elif trang == "Ghim ca / full-time":
        trang_ghim(conn, tuan)
    elif trang == "Thống kê":
        trang_thong_ke(conn, nd, tuan)
    elif trang == "Nhân viên":
        trang_nhan_vien(conn)
    elif trang == "Cài đặt":
        trang_cai_dat(conn)
    else:
        trang_mat_khau(conn, nd)


main()
