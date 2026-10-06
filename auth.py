"""
auth.py - Đăng nhập và phân quyền.

Nguyên tắc: mật khẩu KHÔNG bao giờ lưu nguyên văn. Ta lưu "băm" (hash) = kết quả
một chiều của mật khẩu + muối ngẫu nhiên riêng của từng người. Muốn kiểm tra thì
băm lại mật khẩu vừa nhập rồi so với bản đã lưu.

Module này không có input()/print(). Việc giữ "đang đăng nhập" (session) là của giao diện.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

SO_VONG_BAM = 200_000
MK_TOI_THIEU = 8
SO_LAN_SAI_TOI_DA = 5
PHUT_KHOA = 5

QUYEN = {
    "admin": {"xem_lich", "xep_lich", "sua_lich", "ghim_ca", "quan_ly_nhan_vien",
              "quan_ly_cai_dat", "xem_thong_ke", "quan_ly_tai_khoan", "sua_dang_ky_moi_nguoi"},
    "nhan_vien": {"xem_lich", "dang_ky_ca_cua_minh", "xem_thong_ke_cua_minh"},
}


class TaiKhoanBiKhoa(Exception):
    """Đăng nhập sai quá nhiều lần, tạm khóa."""


def _lay(conn, sql, tham_so=()):
    """Chạy SELECT, trả về dict của dòng đầu tiên (hoặc None). Không phụ thuộc row_factory của kết nối."""
    cur = conn.execute(sql, tham_so)
    row = cur.fetchone()
    if row is None:
        return None
    return {mo_ta[0]: gia_tri for mo_ta, gia_tri in zip(cur.description, row)}


def _bam(mat_khau, muoi_hex):
    return hashlib.pbkdf2_hmac("sha256", mat_khau.encode("utf-8"),
                               bytes.fromhex(muoi_hex), SO_VONG_BAM).hex()


def _kiem_tra_mk(mat_khau):
    if not isinstance(mat_khau, str) or len(mat_khau) < MK_TOI_THIEU:
        raise ValueError(f"Mật khẩu phải có ít nhất {MK_TOI_THIEU} ký tự.")


def _nguoi_dung(row):
    return {"id": row["id"], "ten_dang_nhap": row["ten_dang_nhap"],
            "vai_tro": row["vai_tro"], "nhan_vien_id": row["nhan_vien_id"]}


def tao_tai_khoan(conn, ten_dang_nhap, mat_khau, vai_tro="nhan_vien", ten_nhan_vien=None):
    """Tạo tài khoản. Tài khoản nhân viên phải gắn với một nhân viên có sẵn."""
    ten_dang_nhap = (ten_dang_nhap or "").strip()
    if not ten_dang_nhap:
        raise ValueError("Tên đăng nhập không được để trống.")
    if vai_tro not in QUYEN:
        raise ValueError(f"Vai trò không hợp lệ: {vai_tro}")
    _kiem_tra_mk(mat_khau)
    nv_id = None
    if vai_tro == "nhan_vien":
        if not ten_nhan_vien:
            raise ValueError("Tài khoản nhân viên phải gắn với một nhân viên.")
        row = _lay(conn,"SELECT id FROM nhan_vien WHERE ten = ?", (ten_nhan_vien,))
        if row is None:
            raise ValueError(f"Không có nhân viên tên '{ten_nhan_vien}'.")
        nv_id = row["id"]
    if _lay(conn,"SELECT 1 FROM tai_khoan WHERE ten_dang_nhap = ?", (ten_dang_nhap,)):
        raise ValueError(f"Tên đăng nhập '{ten_dang_nhap}' đã tồn tại.")
    muoi = secrets.token_hex(16)
    conn.execute(
        "INSERT INTO tai_khoan (ten_dang_nhap, mat_khau_bam, muoi, vai_tro, nhan_vien_id) VALUES (?,?,?,?,?)",
        (ten_dang_nhap, _bam(mat_khau, muoi), muoi, vai_tro, nv_id))
    conn.commit()


def tao_admin_dau_tien(conn, ten_dang_nhap, mat_khau):
    """Chỉ tạo được khi chưa có admin nào (dùng lần đầu cài đặt)."""
    if _lay(conn,"SELECT 1 FROM tai_khoan WHERE vai_tro = 'admin'"):
        raise ValueError("Đã có admin rồi.")
    tao_tai_khoan(conn, ten_dang_nhap, mat_khau, vai_tro="admin")


def dang_nhap(conn, ten_dang_nhap, mat_khau, bay_gio=None):
    """Trả về dict người dùng nếu đúng, None nếu sai. Raise TaiKhoanBiKhoa nếu đang bị khóa."""
    bay_gio = bay_gio or datetime.now()
    row = _lay(conn, "SELECT * FROM tai_khoan WHERE ten_dang_nhap = ?", ((ten_dang_nhap or "").strip(),))
    if row is None:
        # vẫn băm một lần để thời gian phản hồi không lộ tài khoản có tồn tại hay không
        _bam(mat_khau or "", "00" * 16)
        return None
    if row["khoa_den"] and datetime.fromisoformat(row["khoa_den"]) > bay_gio:
        raise TaiKhoanBiKhoa(f"Tài khoản bị khóa đến {row['khoa_den']}.")
    dung = hmac.compare_digest(_bam(mat_khau or "", row["muoi"]), row["mat_khau_bam"])
    if dung:
        conn.execute("UPDATE tai_khoan SET so_lan_sai = 0, khoa_den = NULL WHERE id = ?", (row["id"],))
        conn.commit()
        return _nguoi_dung(row)
    sai = row["so_lan_sai"] + 1
    khoa = None
    if sai >= SO_LAN_SAI_TOI_DA:
        khoa = (bay_gio + timedelta(minutes=PHUT_KHOA)).isoformat(timespec="seconds")
        sai = 0
    conn.execute("UPDATE tai_khoan SET so_lan_sai = ?, khoa_den = ? WHERE id = ?", (sai, khoa, row["id"]))
    conn.commit()
    return None


def doi_mat_khau(conn, nguoi_dung, mk_cu, mk_moi):
    row = _lay(conn,"SELECT * FROM tai_khoan WHERE id = ?", (nguoi_dung["id"],))
    if row is None or not hmac.compare_digest(_bam(mk_cu or "", row["muoi"]), row["mat_khau_bam"]):
        raise ValueError("Mật khẩu cũ không đúng.")
    _kiem_tra_mk(mk_moi)
    muoi = secrets.token_hex(16)
    conn.execute("UPDATE tai_khoan SET mat_khau_bam=?, muoi=?, so_lan_sai=0, khoa_den=NULL WHERE id=?",
                 (_bam(mk_moi, muoi), muoi, row["id"]))
    conn.commit()


def dat_lai_mat_khau(conn, nguoi_dung, ten_dang_nhap, mk_moi):
    """Chỉ admin: đặt lại mật khẩu (và mở khóa) cho người khác."""
    yeu_cau_quyen(nguoi_dung, "quan_ly_tai_khoan")
    _kiem_tra_mk(mk_moi)
    row = _lay(conn,"SELECT id FROM tai_khoan WHERE ten_dang_nhap = ?", (ten_dang_nhap,))
    if row is None:
        raise ValueError(f"Không có tài khoản '{ten_dang_nhap}'.")
    muoi = secrets.token_hex(16)
    conn.execute("UPDATE tai_khoan SET mat_khau_bam=?, muoi=?, so_lan_sai=0, khoa_den=NULL WHERE id=?",
                 (_bam(mk_moi, muoi), muoi, row["id"]))
    conn.commit()


def co_quyen(nguoi_dung, hanh_dong):
    return bool(nguoi_dung) and hanh_dong in QUYEN.get(nguoi_dung.get("vai_tro"), set())


def yeu_cau_quyen(nguoi_dung, hanh_dong):
    if not co_quyen(nguoi_dung, hanh_dong):
        raise PermissionError(f"Bạn không có quyền '{hanh_dong}'.")


def co_the_sua_dang_ky(conn, nguoi_dung, ten_nv):
    """Admin sửa được của mọi người; nhân viên chỉ sửa được đăng ký của chính mình."""
    if co_quyen(nguoi_dung, "sua_dang_ky_moi_nguoi"):
        return True
    if not co_quyen(nguoi_dung, "dang_ky_ca_cua_minh"):
        return False
    row = _lay(conn,"SELECT ten FROM nhan_vien WHERE id = ?", (nguoi_dung["nhan_vien_id"],))
    return row is not None and row["ten"] == ten_nv
