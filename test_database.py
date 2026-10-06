import pytest
import database as db
import solver as sv


@pytest.fixture
def conn(tmp_path):
    c = db.ket_noi(str(tmp_path / "t.db"))
    db.khoi_tao(c)
    return c


def them(conn, ten_ds, **kw):
    for t in ten_ds:
        db.them_nhan_vien(conn, t, **kw)


def test_mac_dinh_ngay_ca_co_gio(conn):
    cfg = db.doc_cau_hinh(conn, "2026-10-05")
    assert len(cfg["ngay"]) == 7 and len(cfg["ca"]) == 3
    assert db.so_gio_ca("07:00", "12:00") == 5
    assert db.so_gio_ca("18:00", "02:00") == 8       # qua nửa đêm


def test_gio_khong_hop_le(conn):
    with pytest.raises(ValueError):
        db.kiem_tra_gio("25:00")


def test_nhan_vien_trung_ten_va_loai(conn):
    db.them_nhan_vien(conn, "An")
    assert db.them_nhan_vien(conn, "An") is False      # trùng tên: không thêm, trả False
    assert db.them_nhan_vien(conn, "  ") is False
    with pytest.raises(ValueError):
        db.them_nhan_vien(conn, "B", loai="sai")


def test_dang_ky_theo_tuan_khong_lan_nhau(conn):
    them(conn, ["An"])
    db.luu_dang_ky(conn, "2026-10-05", "An", {("Thứ 2", "Sáng")})
    db.luu_dang_ky(conn, "2026-10-12", "An", {("Thứ 3", "Tối")})
    assert db.doc_dang_ky(conn, "2026-10-05")["An"] == {("Thứ 2", "Sáng")}
    assert db.doc_dang_ky(conn, "2026-10-12")["An"] == {("Thứ 3", "Tối")}
    db.luu_dang_ky(conn, "2026-10-05", "An", {("Thứ 4", "Chiều")})   # ghi đè, không cộng dồn
    assert db.doc_dang_ky(conn, "2026-10-05")["An"] == {("Thứ 4", "Chiều")}


def test_ghim_lam_va_nghi(conn):
    them(conn, ["An"])
    db.dat_ghim(conn, "2026-10-05", "An", {("Thứ 2", "Sáng")})
    db.dat_ghim(conn, "2026-10-05", "An", {("Thứ 3", "Sáng")}, loai="nghi")
    gh, kx = db.doc_ghim(conn, "2026-10-05")
    assert gh["An"] == {("Thứ 2", "Sáng")} and kx["An"] == {("Thứ 3", "Sáng")}


def test_gioi_han_tuan_tuy_chon(conn):
    them(conn, ["An", "Binh"])
    assert db.doc_cau_hinh(conn, "2026-10-05")["toi_da_tuan"] is None     # chưa đặt = không giới hạn
    db.dat_toi_da_tuan(conn, 5)
    assert db.doc_toi_da_tuan(conn) == 5
    db.dat_toi_da_tuan_nhan_vien(conn, "An", 3)
    cfg = db.doc_cau_hinh(conn, "2026-10-05")
    assert cfg["toi_da_tuan"]["An"] == 3 and cfg["toi_da_tuan"]["Binh"] == 5
    db.dat_toi_da_tuan(conn, None)
    assert db.doc_toi_da_tuan(conn) is None


def test_full_time_khong_bi_gioi_han_va_nam_trong_cau_hinh(conn):
    them(conn, ["An"])
    db.them_nhan_vien(conn, "Giang", loai="full_time")
    db.dat_toi_da_tuan(conn, 4)
    cfg = db.doc_cau_hinh(conn, "2026-10-05")
    assert cfg["full_time"] == ["Giang"]
    assert "Giang" not in cfg["toi_da_tuan"]
    db.doi_loai_nhan_vien(conn, "Giang", "part_time")
    assert db.doc_cau_hinh(conn, "2026-10-05")["full_time"] in (None, [])


def test_luu_lich_doc_lich_va_nguon(conn):
    them(conn, ["An", "Binh"])
    db.luu_lich(conn, "2026-10-05", {("Thứ 2", "Sáng"): ["An", "Binh"]})
    lich = db.doc_lich(conn, "2026-10-05")
    assert sorted(lich[("Thứ 2", "Sáng")]) == ["An", "Binh"]
    db.luu_lich(conn, "2026-10-05", {("Thứ 2", "Sáng"): ["An"]})   # lưu lại = thay thế
    assert db.doc_lich(conn, "2026-10-05")[("Thứ 2", "Sáng")] == ["An"]


def test_thong_ke_tuan_thang_va_gio(conn):
    them(conn, ["An", "Binh"])
    db.luu_lich(conn, "2026-10-05", {("Thứ 2", "Sáng"): ["An"], ("Thứ 2", "Tối"): ["An", "Binh"]})
    db.luu_lich(conn, "2026-10-12", {("Thứ 3", "Chiều"): ["An"]})
    t = {r["ten"]: r for r in db.thong_ke_tuan(conn, "2026-10-05")}
    assert t["An"]["so_ca"] == 2 and t["An"]["so_gio"] == 10 and t["An"]["so_ngay"] == 1
    assert t["Binh"]["so_ca"] == 1
    assert t["An"]["so_ca_kho"] == 1                                   # Tối = ca khó
    th = {r["ten"]: r for r in db.thong_ke_thang(conn, 2026, 10)}
    assert th["An"]["so_ca"] == 3 and th["An"]["so_gio"] == 15
    assert {r["ten"]: r["so_ca"] for r in db.thong_ke_thang(conn, 2026, 11)} == {"An": 0, "Binh": 0}


def test_lich_su_va_nhieu_tuan_cong_bang(conn):
    them(conn, [f"N{i}" for i in range(6)])
    for w in ["2026-10-05", "2026-10-12", "2026-10-19"]:
        for i in range(6):
            db.luu_dang_ky(conn, w, f"N{i}", {(d, c) for d in db.doc_cau_hinh(conn, w)["ngay"]
                                              for c in db.doc_cau_hinh(conn, w)["ca"]})
        cfg = db.doc_cau_hinh(conn, w)
        r = sv.xep_lich(**cfg)
        assert r["trang_thai"] in ("OPTIMAL", "FEASIBLE")
        db.luu_lich(conn, w, sv.lich_theo_ca(r["lich"], cfg["nhan_vien"], cfg["ngay"], cfg["ca"]))
    tong = [r["so_ca"] for r in db.thong_ke_thang(conn, 2026, 10)]
    assert sum(tong) == 3 * 42 and max(tong) - min(tong) <= 1
    assert db.doc_cau_hinh(conn, "2026-10-26")["lich_su"]["N0"]["so_ca"] > 0


def test_cu_phap_schema_cu_bi_tu_choi(tmp_path):
    import sqlite3
    p = str(tmp_path / "cu.db")
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE lam_duoc (a)")
    c.commit(); c.close()
    with pytest.raises(RuntimeError):
        db.ket_noi(p)


def test_xoa_nhan_vien_xoa_du_lieu_lien_quan(conn):
    them(conn, ["An"])
    db.luu_dang_ky(conn, "2026-10-05", "An", {("Thứ 2", "Sáng")})
    db.xoa_nhan_vien(conn, "An")
    assert "An" not in db.doc_dang_ky(conn, "2026-10-05")
