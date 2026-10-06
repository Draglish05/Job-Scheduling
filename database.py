"""
database.py - Lưu dữ liệu cửa hàng bằng SQLite (một file .db, có sẵn trong Python).

Dữ liệu lưu lại sau khi tắt chương trình, nên không phải nhập lại mỗi lần.
Như solver.py, file này không có input() hay print(); giao diện nào cũng gọi được.

Một TUẦN được nhận diện bằng ngày bắt đầu (ví dụ "2026-10-05"). Ngày đó là ngày đầu tiên
trong danh sách `ngay`; các ngày sau cộng thêm `lech_ngay` (0, 1, 2...) để ra ngày thật.

Các bảng:
  nhan_vien      : nhân viên, loại (part_time / full_time), giới hạn ca/tuần riêng (tuỳ chọn)
  ngay           : các ngày làm việc trong tuần (thứ tự và độ lệch so với ngày đầu tuần)
  ca             : các loại ca, số người cần, giờ bắt đầu, giờ kết thúc
  so_nguoi_rieng : số người cần cho một ca cụ thể (ghi đè số người của loại ca)
  cap_ca_cam / cap_ca_han_che : cặp ca không được / cố tránh làm chung một ngày
  cai_dat        : cài đặt chung (giới hạn ca/tuần chung, số tuần lịch sử để chia đều...)
  tuan           : các tuần đã dùng
  dang_ky        : ca nhân viên đăng ký làm được, THEO TỪNG TUẦN
  ghim_tuan      : ca admin ghim làm ("lam") hoặc chặn không xếp ("nghi") trong từng tuần
  lich_tuan      : lịch đã xếp của từng tuần (lịch sử), kèm nguồn: may / ghim / full_time / tay
  tai_khoan      : tài khoản đăng nhập (xem auth.py)
"""
import sqlite3
from datetime import date, datetime, timedelta

DUONG_DAN_MAC_DINH = "cua_hang.db"
NGAY_MAC_DINH = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
CA_MAC_DINH = [("Sáng", 2, "07:00", "12:00"), ("Chiều", 2, "12:00", "17:00"), ("Tối", 2, "17:00", "22:00")]
LOAI_NHAN_VIEN = ("part_time", "full_time")
PHIEN_BAN_SCHEMA = 2


# ---------------------------------------------------------------
# Kết nối và tạo bảng
# ---------------------------------------------------------------
def ket_noi(duong_dan=DUONG_DAN_MAC_DINH):
    """Mở (hoặc tạo mới) file dữ liệu và đảm bảo các bảng đã có."""
    conn = sqlite3.connect(duong_dan)
    conn.execute("PRAGMA foreign_keys = ON")   # xóa nhân viên/ca/ngày thì dữ liệu liên quan cũng xóa theo
    khoi_tao(conn)
    return conn


def khoi_tao(conn):
    cu = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='lam_duoc'").fetchone()
    if cu is not None and conn.execute("PRAGMA user_version").fetchone()[0] < PHIEN_BAN_SCHEMA:
        raise RuntimeError("File dữ liệu này theo cấu trúc cũ (chưa có đăng ký theo tuần). "
                           "Hãy xóa file .db cũ hoặc dùng tên file khác để tạo mới.")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS nhan_vien (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ten         TEXT NOT NULL UNIQUE,
        loai        TEXT NOT NULL DEFAULT 'part_time',
        toi_da_tuan INTEGER
    );
    CREATE TABLE IF NOT EXISTS ngay (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        ten      TEXT NOT NULL UNIQUE,
        thu_tu   INTEGER NOT NULL,
        lech_ngay INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS ca (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ten         TEXT NOT NULL UNIQUE,
        so_nguoi    INTEGER NOT NULL CHECK (so_nguoi >= 0),
        thu_tu      INTEGER NOT NULL,
        gio_bat_dau TEXT,
        gio_ket_thuc TEXT
    );
    CREATE TABLE IF NOT EXISTS so_nguoi_rieng (
        ngay_id  INTEGER NOT NULL REFERENCES ngay(id) ON DELETE CASCADE,
        ca_id    INTEGER NOT NULL REFERENCES ca(id) ON DELETE CASCADE,
        so_nguoi INTEGER NOT NULL CHECK (so_nguoi >= 0),
        PRIMARY KEY (ngay_id, ca_id)
    );
    CREATE TABLE IF NOT EXISTS cap_ca_cam (
        ca1_id INTEGER NOT NULL REFERENCES ca(id) ON DELETE CASCADE,
        ca2_id INTEGER NOT NULL REFERENCES ca(id) ON DELETE CASCADE,
        PRIMARY KEY (ca1_id, ca2_id)
    );
    CREATE TABLE IF NOT EXISTS cap_ca_han_che (
        ca1_id INTEGER NOT NULL REFERENCES ca(id) ON DELETE CASCADE,
        ca2_id INTEGER NOT NULL REFERENCES ca(id) ON DELETE CASCADE,
        PRIMARY KEY (ca1_id, ca2_id)
    );
    CREATE TABLE IF NOT EXISTS cai_dat (
        khoa    TEXT PRIMARY KEY,
        gia_tri TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS tuan (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        ngay_bat_dau TEXT NOT NULL UNIQUE
    );
    CREATE TABLE IF NOT EXISTS dang_ky (
        tuan_id      INTEGER NOT NULL REFERENCES tuan(id) ON DELETE CASCADE,
        nhan_vien_id INTEGER NOT NULL REFERENCES nhan_vien(id) ON DELETE CASCADE,
        ngay_id      INTEGER NOT NULL REFERENCES ngay(id) ON DELETE CASCADE,
        ca_id        INTEGER NOT NULL REFERENCES ca(id) ON DELETE CASCADE,
        PRIMARY KEY (tuan_id, nhan_vien_id, ngay_id, ca_id)
    );
    CREATE TABLE IF NOT EXISTS ghim_tuan (
        tuan_id      INTEGER NOT NULL REFERENCES tuan(id) ON DELETE CASCADE,
        nhan_vien_id INTEGER NOT NULL REFERENCES nhan_vien(id) ON DELETE CASCADE,
        ngay_id      INTEGER NOT NULL REFERENCES ngay(id) ON DELETE CASCADE,
        ca_id        INTEGER NOT NULL REFERENCES ca(id) ON DELETE CASCADE,
        loai         TEXT NOT NULL CHECK (loai IN ('lam', 'nghi')),
        PRIMARY KEY (tuan_id, nhan_vien_id, ngay_id, ca_id)
    );
    CREATE TABLE IF NOT EXISTS lich_tuan (
        tuan_id      INTEGER NOT NULL REFERENCES tuan(id) ON DELETE CASCADE,
        ngay_id      INTEGER NOT NULL REFERENCES ngay(id) ON DELETE CASCADE,
        ca_id        INTEGER NOT NULL REFERENCES ca(id) ON DELETE CASCADE,
        nhan_vien_id INTEGER NOT NULL REFERENCES nhan_vien(id) ON DELETE CASCADE,
        nguon        TEXT NOT NULL DEFAULT 'may',
        PRIMARY KEY (tuan_id, ngay_id, ca_id, nhan_vien_id)
    );
    CREATE TABLE IF NOT EXISTS tai_khoan (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        ten_dang_nhap TEXT NOT NULL UNIQUE COLLATE NOCASE,
        mat_khau_bam  TEXT NOT NULL,
        muoi          TEXT NOT NULL,
        vai_tro       TEXT NOT NULL CHECK (vai_tro IN ('admin', 'nhan_vien')),
        nhan_vien_id  INTEGER REFERENCES nhan_vien(id) ON DELETE CASCADE,
        so_lan_sai    INTEGER NOT NULL DEFAULT 0,
        khoa_den      TEXT
    );
    """)
    conn.execute(f"PRAGMA user_version = {PHIEN_BAN_SCHEMA}")
    # Lần đầu dùng: nạp sẵn ngày và ca mặc định để có cái mà chỉnh
    if conn.execute("SELECT COUNT(*) FROM ngay").fetchone()[0] == 0:
        dat_ngay(conn, NGAY_MAC_DINH)
    if conn.execute("SELECT COUNT(*) FROM ca").fetchone()[0] == 0:
        dat_ca(conn, CA_MAC_DINH)
    conn.commit()


# ---------------------------------------------------------------
# Hàm phụ
# ---------------------------------------------------------------
def _id(conn, bang, ten):
    row = conn.execute(f"SELECT id FROM {bang} WHERE ten = ?", (ten,)).fetchone()
    if row is None:
        raise ValueError(f"Không tìm thấy '{ten}' trong bảng {bang}")
    return row[0]


def _ngay(d):
    """Nhận date, datetime hoặc chuỗi 'YYYY-MM-DD', trả về đối tượng date."""
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    try:
        return datetime.strptime(str(d), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"Ngày không hợp lệ: '{d}' (cần dạng YYYY-MM-DD)")


def _tuan_id(conn, ngay_bat_dau, tao=False):
    chuoi = _ngay(ngay_bat_dau).isoformat()
    row = conn.execute("SELECT id FROM tuan WHERE ngay_bat_dau = ?", (chuoi,)).fetchone()
    if row is not None:
        return row[0]
    if not tao:
        raise ValueError(f"Chưa có tuần bắt đầu ngày {chuoi}")
    cur = conn.execute("INSERT INTO tuan (ngay_bat_dau) VALUES (?)", (chuoi,))
    conn.commit()
    return cur.lastrowid


def lay_hoac_tao_tuan(conn, ngay_bat_dau):
    """Trả về id của tuần (tạo mới nếu chưa có)."""
    return _tuan_id(conn, ngay_bat_dau, tao=True)


def ds_tuan(conn):
    """Danh sách ngày bắt đầu của các tuần đã dùng, cũ nhất trước (dạng 'YYYY-MM-DD')."""
    return [r[0] for r in conn.execute("SELECT ngay_bat_dau FROM tuan ORDER BY ngay_bat_dau")]


def kiem_tra_gio(gio):
    """Kiểm tra chuỗi giờ dạng 'HH:MM' (00:00 đến 23:59). Trả về (giờ, phút)."""
    try:
        t = datetime.strptime(gio, "%H:%M")
    except (ValueError, TypeError):
        raise ValueError(f"Giờ không hợp lệ: '{gio}' (cần dạng HH:MM, ví dụ 07:30)")
    return t.hour, t.minute


def so_gio_ca(gio_bat_dau, gio_ket_thuc):
    """
    Số giờ của một ca. Nếu giờ kết thúc nhỏ hơn hoặc bằng giờ bắt đầu thì hiểu là ca qua nửa đêm
    (ví dụ 22:00 đến 02:00 là 4 giờ). Thiếu một trong hai giờ thì trả về 0.
    """
    if not gio_bat_dau or not gio_ket_thuc:
        return 0.0
    h1, m1 = kiem_tra_gio(gio_bat_dau)
    h2, m2 = kiem_tra_gio(gio_ket_thuc)
    phut = (h2 * 60 + m2) - (h1 * 60 + m1)
    if phut <= 0:
        phut += 24 * 60
    return round(phut / 60, 2)


# ---------------------------------------------------------------
# Nhân viên
# ---------------------------------------------------------------
def them_nhan_vien(conn, ten, loai="part_time", toi_da_tuan=None):
    """Thêm nhân viên. Trả về True nếu thêm được, False nếu tên trống hoặc đã tồn tại."""
    ten = ten.strip()
    if ten == "":
        return False
    if loai not in LOAI_NHAN_VIEN:
        raise ValueError(f"Loại nhân viên phải là một trong {LOAI_NHAN_VIEN}")
    if toi_da_tuan is not None and toi_da_tuan < 0:
        raise ValueError("Giới hạn ca/tuần không được âm")
    try:
        conn.execute("INSERT INTO nhan_vien (ten, loai, toi_da_tuan) VALUES (?, ?, ?)",
                     (ten, loai, toi_da_tuan))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def xoa_nhan_vien(conn, ten):
    """Xóa nhân viên (kèm đăng ký, ghim, lịch sử và tài khoản của họ). Trả về True nếu có xóa."""
    cur = conn.execute("DELETE FROM nhan_vien WHERE ten = ?", (ten,))
    conn.commit()
    return cur.rowcount > 0


def doi_loai_nhan_vien(conn, ten, loai):
    """Đổi giữa part_time và full_time."""
    if loai not in LOAI_NHAN_VIEN:
        raise ValueError(f"Loại nhân viên phải là một trong {LOAI_NHAN_VIEN}")
    conn.execute("UPDATE nhan_vien SET loai = ? WHERE id = ?", (loai, _id(conn, "nhan_vien", ten)))
    conn.commit()


def dat_toi_da_tuan_nhan_vien(conn, ten, so_ca=None):
    """Giới hạn ca/tuần RIÊNG cho một người (None = dùng giới hạn chung hoặc không giới hạn)."""
    if so_ca is not None and so_ca < 0:
        raise ValueError("Giới hạn ca/tuần không được âm")
    conn.execute("UPDATE nhan_vien SET toi_da_tuan = ? WHERE id = ?", (so_ca, _id(conn, "nhan_vien", ten)))
    conn.commit()


def ds_nhan_vien(conn):
    return [r[0] for r in conn.execute("SELECT ten FROM nhan_vien ORDER BY id")]


def ds_nhan_vien_chi_tiet(conn):
    """Danh sách dict: ten, loai, toi_da_tuan."""
    return [{"ten": r[0], "loai": r[1], "toi_da_tuan": r[2]}
            for r in conn.execute("SELECT ten, loai, toi_da_tuan FROM nhan_vien ORDER BY id")]


# ---------------------------------------------------------------
# Cài đặt chung
# ---------------------------------------------------------------
def dat_cai_dat(conn, khoa, gia_tri):
    """Lưu một cài đặt. gia_tri = None nghĩa là xóa cài đặt đó."""
    if gia_tri is None:
        conn.execute("DELETE FROM cai_dat WHERE khoa = ?", (khoa,))
    else:
        conn.execute("INSERT OR REPLACE INTO cai_dat (khoa, gia_tri) VALUES (?, ?)", (khoa, str(gia_tri)))
    conn.commit()


def doc_cai_dat(conn, khoa, mac_dinh=None):
    row = conn.execute("SELECT gia_tri FROM cai_dat WHERE khoa = ?", (khoa,)).fetchone()
    return mac_dinh if row is None else row[0]


def dat_toi_da_tuan(conn, so_ca=None):
    """Giới hạn số ca/tuần CHUNG cho mọi nhân viên part-time. None = không giới hạn (tuỳ chọn)."""
    if so_ca is not None and so_ca < 0:
        raise ValueError("Giới hạn ca/tuần không được âm")
    dat_cai_dat(conn, "toi_da_tuan", so_ca)


def doc_toi_da_tuan(conn):
    v = doc_cai_dat(conn, "toi_da_tuan")
    return None if v is None else int(v)


def dat_so_tuan_lich_su(conn, so_tuan):
    """Số tuần gần nhất được dùng để chia đều công bằng nhiều tuần (mặc định 4)."""
    if so_tuan < 0:
        raise ValueError("Số tuần không được âm")
    dat_cai_dat(conn, "so_tuan_lich_su", so_tuan)


def doc_so_tuan_lich_su(conn):
    return int(doc_cai_dat(conn, "so_tuan_lich_su", 4))


# ---------------------------------------------------------------
# Ngày, ca (cấu hình theo nhà hàng)
# ---------------------------------------------------------------
def dat_ngay(conn, ds_ngay):
    """Đặt lại danh sách ngày làm việc, ví dụ ["Thứ 2", ..., "Chủ nhật"]. Dữ liệu của ngày bị bỏ sẽ mất."""
    hien_co = {r[0] for r in conn.execute("SELECT ten FROM ngay")}
    for ten in hien_co:
        if ten not in ds_ngay:
            conn.execute("DELETE FROM ngay WHERE ten = ?", (ten,))
    for i, ten in enumerate(ds_ngay):
        if ten in hien_co:
            conn.execute("UPDATE ngay SET thu_tu = ?, lech_ngay = ? WHERE ten = ?", (i, i, ten))
        else:
            conn.execute("INSERT INTO ngay (ten, thu_tu, lech_ngay) VALUES (?, ?, ?)", (ten, i, i))
    conn.commit()


def dat_ca(conn, ds_ca):
    """
    Đặt lại các loại ca. Mỗi ca là (tên, số người) hoặc (tên, số người, giờ bắt đầu, giờ kết thúc),
    ví dụ [("Sáng", 2, "07:00", "12:00"), ("Tối", 3, "17:00", "22:00")]. Dữ liệu của ca bị bỏ sẽ mất.
    """
    chuan = []
    for item in ds_ca:
        if len(item) == 2:
            ten, so = item
            bd = kt = None
        elif len(item) == 4:
            ten, so, bd, kt = item
        else:
            raise ValueError("Mỗi ca phải là (tên, số người) hoặc (tên, số người, giờ bắt đầu, giờ kết thúc)")
        if (bd is None) != (kt is None):
            raise ValueError(f"Ca '{ten}': phải có đủ cả giờ bắt đầu lẫn giờ kết thúc, hoặc không có giờ nào")
        if bd is not None:
            kiem_tra_gio(bd)
            kiem_tra_gio(kt)
        chuan.append((ten, so, bd, kt))
    ten_moi = [t for t, _, _, _ in chuan]
    hien_co = {r[0] for r in conn.execute("SELECT ten FROM ca")}
    for ten in hien_co:
        if ten not in ten_moi:
            conn.execute("DELETE FROM ca WHERE ten = ?", (ten,))
    for i, (ten, so, bd, kt) in enumerate(chuan):
        if ten in hien_co:
            conn.execute("UPDATE ca SET so_nguoi = ?, thu_tu = ?, gio_bat_dau = ?, gio_ket_thuc = ? WHERE ten = ?",
                         (so, i, bd, kt, ten))
        else:
            conn.execute("INSERT INTO ca (ten, so_nguoi, thu_tu, gio_bat_dau, gio_ket_thuc) VALUES (?, ?, ?, ?, ?)",
                         (ten, so, i, bd, kt))
    conn.commit()


def doc_gio_ca(conn):
    """{tên ca: {"bat_dau": "07:00", "ket_thuc": "12:00", "so_gio": 5.0}} theo thứ tự ca trong ngày."""
    return {r[0]: {"bat_dau": r[1], "ket_thuc": r[2], "so_gio": so_gio_ca(r[1], r[2])}
            for r in conn.execute("SELECT ten, gio_bat_dau, gio_ket_thuc FROM ca ORDER BY thu_tu")}


def dat_so_nguoi_rieng(conn, ten_ngay, ten_ca, so_nguoi):
    """Chỉnh riêng số người cho một ca cụ thể. so_nguoi = None để bỏ chỉnh riêng."""
    ngay_id = _id(conn, "ngay", ten_ngay)
    ca_id = _id(conn, "ca", ten_ca)
    if so_nguoi is None:
        conn.execute("DELETE FROM so_nguoi_rieng WHERE ngay_id = ? AND ca_id = ?", (ngay_id, ca_id))
    else:
        conn.execute("INSERT OR REPLACE INTO so_nguoi_rieng (ngay_id, ca_id, so_nguoi) VALUES (?, ?, ?)",
                     (ngay_id, ca_id, so_nguoi))
    conn.commit()


def _dat_cap(conn, bang, cac_cap):
    conn.execute(f"DELETE FROM {bang}")
    for ten1, ten2 in cac_cap:
        conn.execute(f"INSERT OR IGNORE INTO {bang} (ca1_id, ca2_id) VALUES (?, ?)",
                     (_id(conn, "ca", ten1), _id(conn, "ca", ten2)))
    conn.commit()


def _doc_cap(conn, bang):
    return [(r[0], r[1]) for r in conn.execute(f"""
        SELECT c1.ten, c2.ten FROM {bang} k
        JOIN ca c1 ON c1.id = k.ca1_id JOIN ca c2 ON c2.id = k.ca2_id""")]


def dat_cap_ca_cam(conn, cac_cap):
    """Các cặp ca KHÔNG BAO GIỜ được cùng một người làm trong một ngày (luật cứng). [] để bỏ hết."""
    _dat_cap(conn, "cap_ca_cam", cac_cap)


def doc_cap_ca_cam(conn):
    return _doc_cap(conn, "cap_ca_cam")


def dat_cap_ca_han_che(conn, cac_cap):
    """Các cặp ca máy cố tránh làm chung một ngày, bí mới xếp (luật mềm). [] để bỏ hết."""
    _dat_cap(conn, "cap_ca_han_che", cac_cap)


def doc_cap_ca_han_che(conn):
    return _doc_cap(conn, "cap_ca_han_che")


# ---------------------------------------------------------------
# Đăng ký ca làm được (theo từng tuần)
# ---------------------------------------------------------------
def luu_dang_ky(conn, ngay_bat_dau, ten_nv, cac_o):
    """
    Lưu các ca nhân viên tick làm được trong tuần này, thay thế đăng ký cũ của người đó.
    cac_o = {("Thứ 2", "Sáng"), ("Thứ 3", "Tối"), ...}
    """
    tuan_id = _tuan_id(conn, ngay_bat_dau, tao=True)
    nv_id = _id(conn, "nhan_vien", ten_nv)
    conn.execute("DELETE FROM dang_ky WHERE tuan_id = ? AND nhan_vien_id = ?", (tuan_id, nv_id))
    for ten_ngay, ten_ca in cac_o:
        conn.execute("INSERT INTO dang_ky (tuan_id, nhan_vien_id, ngay_id, ca_id) VALUES (?, ?, ?, ?)",
                     (tuan_id, nv_id, _id(conn, "ngay", ten_ngay), _id(conn, "ca", ten_ca)))
    conn.commit()


def doc_dang_ky(conn, ngay_bat_dau):
    """{tên nhân viên: {(ngày, ca), ...}} của tuần này cho TẤT CẢ nhân viên (chưa đăng ký thì là tập rỗng)."""
    kq = {ten: set() for ten in ds_nhan_vien(conn)}
    row = conn.execute("SELECT id FROM tuan WHERE ngay_bat_dau = ?", (_ngay(ngay_bat_dau).isoformat(),)).fetchone()
    if row is None:
        return kq
    for ten_nv, ten_ngay, ten_ca in conn.execute("""
            SELECT nv.ten, n.ten, c.ten FROM dang_ky d
            JOIN nhan_vien nv ON nv.id = d.nhan_vien_id
            JOIN ngay n ON n.id = d.ngay_id JOIN ca c ON c.id = d.ca_id
            WHERE d.tuan_id = ?""", (row[0],)):
        kq[ten_nv].add((ten_ngay, ten_ca))
    return kq


def sao_chep_dang_ky(conn, tu_ngay_bat_dau, den_ngay_bat_dau):
    """Chép đăng ký của một tuần sang tuần khác làm điểm xuất phát (nhân viên rồi chỉnh lại). Ghi đè đăng ký cũ."""
    nguon = doc_dang_ky(conn, tu_ngay_bat_dau)
    for ten, cac_o in nguon.items():
        luu_dang_ky(conn, den_ngay_bat_dau, ten, cac_o)


# ---------------------------------------------------------------
# Ghim ca và chặn ca (theo từng tuần)
# ---------------------------------------------------------------
def dat_ghim(conn, ngay_bat_dau, ten_nv, cac_o, loai="lam"):
    """
    Đặt lại các ca ghim của một người trong tuần. loai = "lam" (bắt buộc làm) hoặc "nghi" (không được xếp).
    Với nhân viên full-time, các ca "lam" chính là lịch do admin xếp tay cho họ.
    cac_o = {("Thứ 2", "Sáng"), ...}; truyền tập rỗng để bỏ hết.
    """
    if loai not in ("lam", "nghi"):
        raise ValueError("loai phải là 'lam' hoặc 'nghi'")
    tuan_id = _tuan_id(conn, ngay_bat_dau, tao=True)
    nv_id = _id(conn, "nhan_vien", ten_nv)
    conn.execute("DELETE FROM ghim_tuan WHERE tuan_id = ? AND nhan_vien_id = ? AND loai = ?", (tuan_id, nv_id, loai))
    for ten_ngay, ten_ca in cac_o:
        conn.execute("INSERT OR REPLACE INTO ghim_tuan (tuan_id, nhan_vien_id, ngay_id, ca_id, loai) VALUES (?, ?, ?, ?, ?)",
                     (tuan_id, nv_id, _id(conn, "ngay", ten_ngay), _id(conn, "ca", ten_ca), loai))
    conn.commit()


def doc_ghim(conn, ngay_bat_dau):
    """Trả về (ghim, khong_xep): hai dict {tên: {(ngày, ca), ...}} chỉ gồm những người có ghim."""
    ghim, khong_xep = {}, {}
    row = conn.execute("SELECT id FROM tuan WHERE ngay_bat_dau = ?", (_ngay(ngay_bat_dau).isoformat(),)).fetchone()
    if row is None:
        return ghim, khong_xep
    for ten_nv, ten_ngay, ten_ca, loai in conn.execute("""
            SELECT nv.ten, n.ten, c.ten, g.loai FROM ghim_tuan g
            JOIN nhan_vien nv ON nv.id = g.nhan_vien_id
            JOIN ngay n ON n.id = g.ngay_id JOIN ca c ON c.id = g.ca_id
            WHERE g.tuan_id = ?""", (row[0],)):
        dich = ghim if loai == "lam" else khong_xep
        dich.setdefault(ten_nv, set()).add((ten_ngay, ten_ca))
    return ghim, khong_xep


# ---------------------------------------------------------------
# Gói dữ liệu để đưa thẳng vào solver
# ---------------------------------------------------------------
def doc_lich_su(conn, ngay_bat_dau, so_tuan=None):
    """
    Số ca đã làm của từng người trong `so_tuan` tuần ngay TRƯỚC tuần này (mặc định lấy từ cài đặt, 4 tuần).
    Trả về {tên: {"so_ca": n, "so_ca_kho": m}}. Ca khó là ca cuối cùng trong ngày.
    """
    so_tuan = doc_so_tuan_lich_su(conn) if so_tuan is None else so_tuan
    d = _ngay(ngay_bat_dau)
    tu, den = (d - timedelta(days=7 * so_tuan)).isoformat(), d.isoformat()
    ca_cuoi = conn.execute("SELECT id FROM ca ORDER BY thu_tu DESC LIMIT 1").fetchone()
    ca_cuoi = ca_cuoi[0] if ca_cuoi else None
    kq = {ten: {"so_ca": 0, "so_ca_kho": 0} for ten in ds_nhan_vien(conn)}
    for ten, so_ca, so_kho in conn.execute("""
            SELECT nv.ten, COUNT(*), SUM(CASE WHEN l.ca_id = ? THEN 1 ELSE 0 END)
            FROM lich_tuan l
            JOIN tuan t ON t.id = l.tuan_id
            JOIN nhan_vien nv ON nv.id = l.nhan_vien_id
            WHERE t.ngay_bat_dau >= ? AND t.ngay_bat_dau < ?
            GROUP BY nv.ten""", (ca_cuoi, tu, den)):
        kq[ten] = {"so_ca": so_ca, "so_ca_kho": so_kho or 0}
    return kq


def doc_cau_hinh(conn, ngay_bat_dau):
    """
    Trả về dict có đúng tên tham số của xep_lich(), dùng như: xep_lich(**doc_cau_hinh(conn, "2026-10-05")).
    Gồm: danh sách nhân viên/ngày/ca, số người, đăng ký của TUẦN NÀY, ghim/chặn của tuần này,
    nhân viên full-time, giới hạn ca/tuần (chung hoặc riêng), cặp ca cấm/hạn chế, lịch sử các tuần trước.
    """
    chi_tiet = ds_nhan_vien_chi_tiet(conn)
    nhan_vien = [x["ten"] for x in chi_tiet]
    full_time = [x["ten"] for x in chi_tiet if x["loai"] == "full_time"]
    chung = doc_toi_da_tuan(conn)
    gioi_han = {}
    for x in chi_tiet:
        if x["loai"] == "full_time":
            continue
        gh = x["toi_da_tuan"] if x["toi_da_tuan"] is not None else chung
        if gh is not None:
            gioi_han[x["ten"]] = gh
    ngay = [r[0] for r in conn.execute("SELECT ten FROM ngay ORDER BY thu_tu")]
    ca_rows = list(conn.execute("SELECT ten, so_nguoi FROM ca ORDER BY thu_tu"))
    rieng = {}
    for ten_ngay, ten_ca, so in conn.execute("""
            SELECT n.ten, c.ten, r.so_nguoi FROM so_nguoi_rieng r
            JOIN ngay n ON n.id = r.ngay_id JOIN ca c ON c.id = r.ca_id"""):
        rieng[(ten_ngay, ten_ca)] = so
    ghim, khong_xep = doc_ghim(conn, ngay_bat_dau)
    return {
        "nhan_vien": nhan_vien,
        "ngay": ngay,
        "ca": [t for t, _ in ca_rows],
        "so_nguoi": {t: so for t, so in ca_rows},
        "lam_duoc": doc_dang_ky(conn, ngay_bat_dau),
        "so_nguoi_rieng": rieng or None,
        "toi_da_tuan": gioi_han or None,
        "cap_ca_cam": doc_cap_ca_cam(conn) or None,
        "cap_ca_han_che": doc_cap_ca_han_che(conn) or None,
        "ghim": ghim or None,
        "khong_xep": khong_xep or None,
        "full_time": full_time or None,
        "lich_su": doc_lich_su(conn, ngay_bat_dau),
    }


# ---------------------------------------------------------------
# Lưu và đọc lịch đã xếp (lịch sử theo tuần)
# ---------------------------------------------------------------
def luu_lich(conn, ngay_bat_dau, lich_ca):
    """
    Lưu lịch của một tuần, dạng {(ngày, ca): [tên những người làm]} (kết quả của solver.lich_theo_ca).
    Thay thế lịch cũ của tuần đó. Mỗi dòng được ghi nguồn: full_time (nhân viên full-time),
    ghim (ca admin ghim), hoặc may (do máy xếp).
    """
    tuan_id = _tuan_id(conn, ngay_bat_dau, tao=True)
    loai = {x["ten"]: x["loai"] for x in ds_nhan_vien_chi_tiet(conn)}
    ghim, _ = doc_ghim(conn, ngay_bat_dau)
    conn.execute("DELETE FROM lich_tuan WHERE tuan_id = ?", (tuan_id,))
    for (ten_ngay, ten_ca), ds in lich_ca.items():
        for ten_nv in ds:
            if loai.get(ten_nv) == "full_time":
                nguon = "full_time"
            elif (ten_ngay, ten_ca) in ghim.get(ten_nv, set()):
                nguon = "ghim"
            else:
                nguon = "may"
            conn.execute("INSERT INTO lich_tuan (tuan_id, ngay_id, ca_id, nhan_vien_id, nguon) VALUES (?, ?, ?, ?, ?)",
                         (tuan_id, _id(conn, "ngay", ten_ngay), _id(conn, "ca", ten_ca), _id(conn, "nhan_vien", ten_nv), nguon))
    conn.commit()


def doc_lich(conn, ngay_bat_dau):
    """Đọc lịch đã lưu của một tuần: {(ngày, ca): [tên]} (ca chưa có ai thì là danh sách rỗng)."""
    kq = {}
    ds_ca = [r[0] for r in conn.execute("SELECT ten FROM ca ORDER BY thu_tu")]
    for n in conn.execute("SELECT ten FROM ngay ORDER BY thu_tu").fetchall():
        for c in ds_ca:
            kq[(n[0], c)] = []
    row = conn.execute("SELECT id FROM tuan WHERE ngay_bat_dau = ?", (_ngay(ngay_bat_dau).isoformat(),)).fetchone()
    if row is None:
        return kq
    for ten_ngay, ten_ca, ten_nv in conn.execute("""
            SELECT n.ten, c.ten, nv.ten FROM lich_tuan l
            JOIN ngay n ON n.id = l.ngay_id JOIN ca c ON c.id = l.ca_id
            JOIN nhan_vien nv ON nv.id = l.nhan_vien_id
            WHERE l.tuan_id = ? ORDER BY nv.id""", (row[0],)):
        kq[(ten_ngay, ten_ca)].append(ten_nv)
    return kq


def sua_lich_tay(conn, ngay_bat_dau, ten_nv, ten_ngay, ten_ca, co_lam):
    """Admin chỉnh tay một ô của lịch đã lưu: co_lam=True thêm người vào ca, False bỏ người khỏi ca."""
    tuan_id = _tuan_id(conn, ngay_bat_dau)
    nv_id, ngay_id, ca_id = _id(conn, "nhan_vien", ten_nv), _id(conn, "ngay", ten_ngay), _id(conn, "ca", ten_ca)
    if co_lam:
        conn.execute("INSERT OR REPLACE INTO lich_tuan (tuan_id, ngay_id, ca_id, nhan_vien_id, nguon) VALUES (?, ?, ?, ?, 'tay')",
                     (tuan_id, ngay_id, ca_id, nv_id))
    else:
        conn.execute("DELETE FROM lich_tuan WHERE tuan_id = ? AND ngay_id = ? AND ca_id = ? AND nhan_vien_id = ?",
                     (tuan_id, ngay_id, ca_id, nv_id))
    conn.commit()


# ---------------------------------------------------------------
# Thống kê số ca, số giờ theo tuần / tháng / khoảng ngày bất kỳ
# ---------------------------------------------------------------
def thong_ke(conn, tu_ngay, den_ngay):
    """
    Thống kê từ lịch đã lưu, cho các ca có ngày thật nằm trong [tu_ngay, den_ngay] (tính cả hai đầu).
    Ngày thật của một ca = ngày bắt đầu của tuần + lech_ngay của ngày đó.
    Trả về danh sách dict theo thứ tự nhân viên: ten, loai, so_ca, so_gio, so_ca_kho, so_ngay.
    Nhân viên không có ca nào vẫn có mặt với các số 0. Ca khó là ca cuối cùng trong ngày.
    """
    tu, den = _ngay(tu_ngay), _ngay(den_ngay)
    if den < tu:
        raise ValueError("Ngày kết thúc phải sau hoặc bằng ngày bắt đầu")
    ca_cuoi = conn.execute("SELECT id FROM ca ORDER BY thu_tu DESC LIMIT 1").fetchone()
    ca_cuoi = ca_cuoi[0] if ca_cuoi else None
    kq = {x["ten"]: {"ten": x["ten"], "loai": x["loai"], "so_ca": 0, "so_gio": 0.0, "so_ca_kho": 0, "ngay_lam": set()}
          for x in ds_nhan_vien_chi_tiet(conn)}
    for ten, bat_dau_tuan, lech, ca_id, bd, kt in conn.execute("""
            SELECT nv.ten, t.ngay_bat_dau, n.lech_ngay, c.id, c.gio_bat_dau, c.gio_ket_thuc
            FROM lich_tuan l
            JOIN tuan t ON t.id = l.tuan_id
            JOIN nhan_vien nv ON nv.id = l.nhan_vien_id
            JOIN ngay n ON n.id = l.ngay_id
            JOIN ca c ON c.id = l.ca_id"""):
        ngay_that = _ngay(bat_dau_tuan) + timedelta(days=lech)
        if not (tu <= ngay_that <= den):
            continue
        r = kq[ten]
        r["so_ca"] += 1
        r["so_gio"] = round(r["so_gio"] + so_gio_ca(bd, kt), 2)
        r["so_ca_kho"] += 1 if ca_id == ca_cuoi else 0
        r["ngay_lam"].add(ngay_that)
    out = []
    for r in kq.values():
        r["so_ngay"] = len(r.pop("ngay_lam"))
        out.append(r)
    return out


def thong_ke_tuan(conn, ngay_bat_dau):
    """Thống kê đúng một tuần (7 ngày kể từ ngày bắt đầu)."""
    d = _ngay(ngay_bat_dau)
    return thong_ke(conn, d, d + timedelta(days=6))


def thong_ke_thang(conn, nam, thang):
    """Thống kê một tháng dương lịch, tính theo ngày thật của từng ca."""
    if not 1 <= thang <= 12:
        raise ValueError("Tháng phải từ 1 đến 12")
    dau = date(nam, thang, 1)
    cuoi = (date(nam + 1, 1, 1) if thang == 12 else date(nam, thang + 1, 1)) - timedelta(days=1)
    return thong_ke(conn, dau, cuoi)
