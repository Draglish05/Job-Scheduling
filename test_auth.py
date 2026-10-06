import pytest
from datetime import datetime, timedelta
import database as db, auth


@pytest.fixture
def conn(tmp_path):
    c = db.ket_noi(str(tmp_path / "t.db"))
    db.khoi_tao(c)
    db.them_nhan_vien(c, "An")
    db.them_nhan_vien(c, "Binh")
    return c


def test_tao_va_dang_nhap(conn):
    auth.tao_admin_dau_tien(conn, "chu", "matkhau123")
    u = auth.dang_nhap(conn, "CHU", "matkhau123")
    assert u["vai_tro"] == "admin"
    assert auth.dang_nhap(conn, "chu", "saimatkhau") is None
    assert auth.dang_nhap(conn, "khongco", "matkhau123") is None


def test_mat_khau_khong_luu_nguyen_van(conn):
    auth.tao_admin_dau_tien(conn, "chu", "matkhau123")
    r = conn.execute("SELECT mat_khau_bam FROM tai_khoan").fetchone()
    assert "matkhau123" not in r[0]


def test_mk_ngan_va_trung_ten(conn):
    with pytest.raises(ValueError):
        auth.tao_admin_dau_tien(conn, "chu", "123")
    auth.tao_admin_dau_tien(conn, "chu", "matkhau123")
    with pytest.raises(ValueError):
        auth.tao_admin_dau_tien(conn, "khac", "matkhau123")  # đã có admin
    with pytest.raises(ValueError):
        auth.tao_tai_khoan(conn, "CHU", "matkhau123", "nhan_vien", "An")  # trùng tên (không phân biệt hoa thường)


def test_nhan_vien_phai_gan_nhan_vien_co_that(conn):
    with pytest.raises(ValueError):
        auth.tao_tai_khoan(conn, "x", "matkhau123", "nhan_vien", None)
    with pytest.raises(ValueError):
        auth.tao_tai_khoan(conn, "x", "matkhau123", "nhan_vien", "NguoiLa")


def test_khoa_sau_nhieu_lan_sai(conn):
    auth.tao_tai_khoan(conn, "an", "matkhau123", "nhan_vien", "An")
    t = datetime(2026, 10, 6, 9, 0)
    for _ in range(auth.SO_LAN_SAI_TOI_DA):
        assert auth.dang_nhap(conn, "an", "sai", bay_gio=t) is None
    with pytest.raises(auth.TaiKhoanBiKhoa):
        auth.dang_nhap(conn, "an", "matkhau123", bay_gio=t + timedelta(minutes=1))
    assert auth.dang_nhap(conn, "an", "matkhau123", bay_gio=t + timedelta(minutes=auth.PHUT_KHOA + 1))


def test_doi_va_dat_lai_mat_khau(conn):
    auth.tao_admin_dau_tien(conn, "chu", "matkhau123")
    auth.tao_tai_khoan(conn, "an", "matkhau123", "nhan_vien", "An")
    admin = auth.dang_nhap(conn, "chu", "matkhau123")
    an = auth.dang_nhap(conn, "an", "matkhau123")
    with pytest.raises(ValueError):
        auth.doi_mat_khau(conn, an, "saicu", "matkhaumoi1")
    auth.doi_mat_khau(conn, an, "matkhau123", "matkhaumoi1")
    assert auth.dang_nhap(conn, "an", "matkhaumoi1")
    with pytest.raises(PermissionError):
        auth.dat_lai_mat_khau(conn, an, "chu", "hackhackhack")
    auth.dat_lai_mat_khau(conn, admin, "an", "datlai12345")
    assert auth.dang_nhap(conn, "an", "datlai12345")


def test_phan_quyen(conn):
    auth.tao_admin_dau_tien(conn, "chu", "matkhau123")
    auth.tao_tai_khoan(conn, "an", "matkhau123", "nhan_vien", "An")
    admin = auth.dang_nhap(conn, "chu", "matkhau123")
    an = auth.dang_nhap(conn, "an", "matkhau123")
    assert auth.co_quyen(admin, "xep_lich") and not auth.co_quyen(an, "xep_lich")
    assert auth.co_quyen(an, "xem_lich")
    with pytest.raises(PermissionError):
        auth.yeu_cau_quyen(an, "ghim_ca")
    assert auth.co_the_sua_dang_ky(conn, an, "An")
    assert not auth.co_the_sua_dang_ky(conn, an, "Binh")
    assert auth.co_the_sua_dang_ky(conn, admin, "Binh")
    assert not auth.co_quyen(None, "xem_lich")


def test_xoa_nhan_vien_xoa_tai_khoan(conn):
    auth.tao_tai_khoan(conn, "an", "matkhau123", "nhan_vien", "An")
    db.xoa_nhan_vien(conn, "An")
    assert auth.dang_nhap(conn, "an", "matkhau123") is None
