import pytest
import solver as sv

NG = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
CA = ["Sáng", "Chiều", "Tối"]
NV = ["A", "B", "C", "D", "E", "F"]
SO2 = {c: 2 for c in CA}
SO1 = {c: 1 for c in CA}


def tat_ca(ds=NV):
    return {n: {(d, c) for d in NG for c in CA} for n in ds}


def chay(**kw):
    tham_so = dict(nhan_vien=NV, ngay=NG, ca=CA, so_nguoi=SO2, lam_duoc=tat_ca())
    tham_so.update(kw)
    return tham_so, sv.xep_lich(**tham_so)


def o_cua(r, nv, ngay=NG, ca=CA):
    e = r_nv(r).index(nv)
    return {(ngay[d], ca[s]) for d in range(len(ngay)) for s in range(len(ca)) if r["lich"][e][d][s]}


def r_nv(r):
    return NV


def test_moi_ca_du_nguoi():
    p, r = chay()
    assert r["trang_thai"] in ("OPTIMAL", "FEASIBLE")
    for d in range(7):
        for s in range(3):
            assert sum(r["lich"][e][d][s] for e in range(6)) == 2


def test_chi_xep_vao_o_da_dang_ky():
    ld = tat_ca()
    ld["A"] = {("T2", "Sáng")}
    _, r = chay(lam_duoc=ld)
    assert o_cua(r, "A") <= {("T2", "Sáng")}


def test_gioi_han_tuan_int_dict_none():
    nv8 = NV + ["G", "H"]
    _, r = chay(nhan_vien=nv8, lam_duoc=tat_ca(nv8), toi_da_tuan=6)
    assert all(x <= 6 for x in r["so_ca"])
    _, r = chay(nhan_vien=nv8, lam_duoc=tat_ca(nv8), toi_da_tuan={"A": 2})
    assert r["so_ca"][0] <= 2
    _, r = chay(toi_da_tuan=None)
    assert r["trang_thai"] in ("OPTIMAL", "FEASIBLE")


def test_gioi_han_qua_chat_thi_vo_nghiem():
    _, r = chay(toi_da_tuan=1)
    assert r["trang_thai"] == "INFEASIBLE"


def test_ghim_bat_buoc_ke_ca_khong_dang_ky():
    ld = tat_ca()
    ld["A"] = set()
    _, r = chay(lam_duoc=ld, ghim={"A": {("T2", "Sáng")}})
    assert ("T2", "Sáng") in o_cua(r, "A")


def test_khong_xep_chan_o():
    _, r = chay(khong_xep={"A": {("T2", "Sáng"), ("T3", "Tối")}})
    assert not (o_cua(r, "A") & {("T2", "Sáng"), ("T3", "Tối")})


def test_ghim_va_khong_xep_mau_thuan():
    with pytest.raises(ValueError):
        chay(ghim={"A": {("T2", "Sáng")}}, khong_xep={"A": {("T2", "Sáng")}})


def test_full_time_chi_co_o_ghim_va_van_dem_vao_so_nguoi():
    gh = {"F": {("T2", "Sáng"), ("T3", "Chiều")}}
    _, r = chay(full_time=["F"], ghim=gh)
    assert o_cua(r, "F") == gh["F"]
    for d in range(7):
        for s in range(3):
            assert sum(r["lich"][e][d][s] for e in range(6)) == 2
    # full-time không bị tính vào giới hạn tuần
    nv8 = NV + ["G", "H"]
    _, r2 = chay(nhan_vien=nv8, lam_duoc=tat_ca(nv8), full_time=["F"],
                 ghim={"F": {(d, c) for d in NG for c in CA}}, toi_da_tuan=6)
    assert r2["so_ca"][5] == 21


def test_cong_bang_nhieu_tuan_nguoi_da_lam_nhieu_thi_lam_it():
    # A đã làm rất nhiều trong lịch sử => tuần này A nên ít ca hơn hẳn
    _, r = chay(lich_su={"A": {"so_ca": 30, "so_ca_kho": 10}})
    ca_a = r["so_ca"][0]
    con_lai = [r["so_ca"][i] for i in range(1, 6)]
    assert ca_a < min(con_lai)
    _, r0 = chay()
    assert max(r0["so_ca"]) - min(r0["so_ca"]) <= 1


def test_chan_doan_thieu_nguoi():
    ld = tat_ca(["A"])
    ld.update({n: set() for n in NV[1:]})
    ds = sv.chan_doan(NV, NG, CA, SO2, lam_duoc=ld, toi_da_tuan=None, cap_ca_cam=None)
    assert any(v["loai"] == "thieu_nguoi" for v in ds)


def test_chan_doan_gioi_han_tuan():
    ds = sv.chan_doan(NV, NG, CA, SO2, lam_duoc=tat_ca(), toi_da_tuan=1, cap_ca_cam=None)
    assert any(v["loai"] in ("gioi_han_tuan", "mau_thuan") for v in ds)


def test_tu_van_noi_long_khi_dong_y():
    # 3 người, mỗi ca 2 người, cấm Sáng+Tối cùng ngày: phải nới mới xếp được
    nv = ["A", "B", "C"]
    ld = {n: {(d, c) for d in NG for c in CA} for n in nv}
    kq = sv.xep_lich_tu_van(nv, NG, CA, SO2, hoi=lambda *_: True, lam_duoc=ld,
                            cap_ca_cam=[("Sáng", "Tối")])
    assert kq["ket_qua"]["trang_thai"] in ("OPTIMAL", "FEASIBLE")
    kq2 = sv.xep_lich_tu_van(nv, NG, CA, SO2, hoi=lambda *_: False, lam_duoc=ld,
                             cap_ca_cam=[("Sáng", "Tối")])
    assert kq2["ket_qua"]["trang_thai"] == "INFEASIBLE"


def test_luat_mem_khong_xep_ca_lien_nhau_khi_du_nguoi():
    _, r = chay(so_nguoi=SO1)
    assert r["so_cap_lien_nhau"] == 0
