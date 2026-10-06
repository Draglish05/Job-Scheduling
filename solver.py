"""
solver.py - Lõi xếp lịch bằng CP-SAT.

Quy ước: file này KHÔNG có input() và KHÔNG tự in ra màn hình.
Giao diện nào (notebook, Streamlit, ...) cũng chỉ việc gọi hàm rồi tự hiển thị.

Mọi dữ liệu vào đều dùng TÊN (tên nhân viên, tên ngày, tên ca), nên mỗi nhà hàng
có thể tự đặt số ca, tên ca và số người mỗi ca.
"""
from ortools.sat.python import cp_model

# Trọng số mặc định. Số càng lớn thì solver càng cố tránh/đạt điều đó.
TRONG_SO_MAC_DINH = {
    "lien_nhau": 5,    # phạt mỗi cặp ca liền nhau TRONG CÙNG MỘT NGÀY (ví dụ Chiều rồi Tối)
    "deu_ca": 1,       # phạt chênh lệch tổng số ca (người nhiều nhất - ít nhất)
    "deu_ca_kho": 2,   # phạt chênh lệch số ca "khó" (ví dụ ca Tối)
    "mong_muon": 1,    # thưởng cho mỗi ca mong muốn được xếp trúng
    "cung_ngay": 4,    # phạt mỗi lần một người làm cả hai ca trong cặp "hạn chế" (ví dụ Sáng + Tối)
    "qua_dem": 5,      # phạt mỗi lần làm ca Tối hôm trước rồi ca Sáng hôm sau (ca qua đêm)
}


# ---------------------------------------------------------------
# Các hàm phụ: đổi dữ liệu theo tên thành bảng theo số thứ tự
# ---------------------------------------------------------------
def _kiem_tra_ten(nhan_vien, ngay, ca):
    for ten_nhom, ds in (("nhân viên", nhan_vien), ("ngày", ngay), ("ca", ca)):
        if len(ds) == 0:
            raise ValueError(f"Danh sách {ten_nhom} đang trống")
        if len(set(ds)) != len(ds):
            raise ValueError(f"Danh sách {ten_nhom} có tên bị trùng")


def _ma_tran_so_nguoi(ngay, ca, so_nguoi, so_nguoi_rieng=None):
    """need[d][s] = số người cần cho ngày d, ca s."""
    for c in ca:
        if c not in so_nguoi:
            raise ValueError(f"Chưa khai báo số người cho ca '{c}'")
    need = [[so_nguoi[c] for c in ca] for _ in ngay]
    for (n, c), v in (so_nguoi_rieng or {}).items():
        if n not in ngay or c not in ca:
            raise ValueError(f"Ngày hoặc ca không tồn tại: ({n}, {c})")
        need[ngay.index(n)][ca.index(c)] = v
    return need


def _ma_tran_theo_ten(nhan_vien, ngay, ca, du_lieu, mac_dinh_tat_ca):
    """
    Đổi {tên nhân viên: {(ngày, ca), ...}} thành bảng ok[e][d][s] (True/False).
    Nếu du_lieu là None thì tất cả đều True (mac_dinh_tat_ca=True) hoặc đều False.
    """
    if du_lieu is None:
        return [[[mac_dinh_tat_ca] * len(ca) for _ in ngay] for _ in nhan_vien]
    ok = [[[False] * len(ca) for _ in ngay] for _ in nhan_vien]
    for ten, cac_o in du_lieu.items():
        if ten not in nhan_vien:
            raise ValueError(f"Không có nhân viên tên '{ten}'")
        e = nhan_vien.index(ten)
        for n, c in cac_o:
            if n not in ngay or c not in ca:
                raise ValueError(f"Ngày hoặc ca không tồn tại: ({n}, {c})")
            ok[e][ngay.index(n)][ca.index(c)] = True
    return ok


def _cap_cam_chi_so(ca, cap_ca_cam):
    """Đổi [("Sáng", "Tối")] thành [(0, 2)] và kiểm tra tên ca có hợp lệ không."""
    kq = []
    for c1, c2 in (cap_ca_cam or []):
        if c1 not in ca or c2 not in ca:
            raise ValueError(f"Cặp ca cấm không hợp lệ: ({c1}, {c2})")
        if c1 == c2:
            raise ValueError(f"Cặp ca cấm phải gồm hai ca khác nhau: ({c1}, {c2})")
        kq.append((ca.index(c1), ca.index(c2)))
    return kq


def _cap_qua_dem_chi_so(ca, cap_ca_qua_dem):
    """Mặc định: ca cuối ngày hôm trước + ca đầu ngày hôm sau (cần ít nhất 2 ca/ngày)."""
    if cap_ca_qua_dem is None:
        cap_ca_qua_dem = [(ca[-1], ca[0])] if len(ca) >= 2 else []
    kq = []
    for c1, c2 in cap_ca_qua_dem:
        if c1 not in ca or c2 not in ca:
            raise ValueError(f"Cặp ca qua đêm không hợp lệ: ({c1}, {c2})")
        kq.append((ca.index(c1), ca.index(c2)))
    return kq


def _gioi_han_tuan(nhan_vien, toi_da_tuan):
    """Danh sách giới hạn ca/tuần của từng nhân viên: một số nguyên hoặc None (không giới hạn).
    toi_da_tuan có thể là: None, một số (áp dụng cho tất cả), hoặc dict {tên: số} (người không có tên trong dict thì không giới hạn)."""
    if toi_da_tuan is None:
        return [None] * len(nhan_vien)
    if isinstance(toi_da_tuan, dict):
        for ten in toi_da_tuan:
            if ten not in nhan_vien:
                raise ValueError(f"Không có nhân viên tên '{ten}' (giới hạn ca/tuần)")
        return [toi_da_tuan.get(ten) for ten in nhan_vien]
    return [toi_da_tuan] * len(nhan_vien)


def _chuan_bi_dang_ky(nhan_vien, ngay, ca, lam_duoc, ghim=None, khong_xep=None, full_time=None):
    """
    Gộp đăng ký + ghim + chặn + full-time thành ba thứ solver cần:
      ok[e][d][s]       : người e có thể được xếp vào (ngày d, ca s) hay không
      bat_buoc[e][d][s] : ca này BẮT BUỘC phải xếp cho người e (ghim làm, hoặc ca cố định của full-time)
      co_dinh           : tập số thứ tự những nhân viên full-time (admin tự xếp, máy không đụng tới)
    """
    ok = _ma_tran_theo_ten(nhan_vien, ngay, ca, lam_duoc, True)
    gh = _ma_tran_theo_ten(nhan_vien, ngay, ca, ghim, False)
    kx = _ma_tran_theo_ten(nhan_vien, ngay, ca, khong_xep, False)
    co_dinh = set()
    for ten in (full_time or []):
        if ten not in nhan_vien:
            raise ValueError(f"Không có nhân viên full-time tên '{ten}'")
        co_dinh.add(nhan_vien.index(ten))
    for e, ten in enumerate(nhan_vien):
        for d in range(len(ngay)):
            for s in range(len(ca)):
                if e in co_dinh:
                    ok[e][d][s] = gh[e][d][s]            # full-time chỉ làm đúng các ca admin đã xếp
                    continue
                if gh[e][d][s] and kx[e][d][s]:
                    raise ValueError(f"{ten}: {ngay[d]} - {ca[s]} vừa bị ghim làm vừa bị chặn không xếp")
                if kx[e][d][s]:
                    ok[e][d][s] = False
                if gh[e][d][s]:
                    ok[e][d][s] = True                    # admin ghim thì được phép dù chưa đăng ký
    return ok, gh, co_dinh


def _lich_su_so(nhan_vien, lich_su):
    """Đổi {tên: {"so_ca": n, "so_ca_kho": m}} thành hai list theo thứ tự nhân viên (thiếu thì là 0)."""
    cu, cu_kho = [0] * len(nhan_vien), [0] * len(nhan_vien)
    for ten, v in (lich_su or {}).items():
        if ten not in nhan_vien:
            continue                                       # nhân viên đã nghỉ việc, bỏ qua lịch sử của họ
        e = nhan_vien.index(ten)
        cu[e] = int(v.get("so_ca", 0))
        cu_kho[e] = int(v.get("so_ca_kho", 0))
    return cu, cu_kho


# ---------------------------------------------------------------
# Hàm chính: xếp lịch
# ---------------------------------------------------------------
def xep_lich(nhan_vien, ngay, ca, so_nguoi, lam_duoc=None, so_nguoi_rieng=None,
             mong_muon=None, toi_da_tuan=None, ca_kho=None, trong_so=None,
             thoi_gian_toi_da=10, cap_ca_cam=None, cap_ca_han_che=None, cap_ca_qua_dem=None,
             ghim=None, khong_xep=None, full_time=None, lich_su=None):
    """
    Xếp lịch cho một tuần.

    nhan_vien : list tên nhân viên, ví dụ ["An", "Binh"]
    ngay      : list tên ngày, ví dụ ["Thứ 2", ..., "Chủ nhật"]
    ca        : list tên ca theo thứ tự trong ngày, ví dụ ["Sáng", "Chiều", "Tối"]
    so_nguoi  : dict số người cần cho mỗi LOẠI ca, ví dụ {"Sáng": 2, "Chiều": 2, "Tối": 3}
    lam_duoc  : dict {tên nhân viên: {(ngày, ca), ...}} các ca nhân viên làm được.
                None = ai cũng làm được mọi ca. Nhân viên không có trong dict = không làm được ca nào.
    so_nguoi_rieng : dict {(ngày, ca): số người} để chỉnh riêng một ca cụ thể (không bắt buộc)
    mong_muon : cùng dạng với lam_duoc, các ca nhân viên MUỐN làm (không bắt buộc)
    toi_da_tuan : giới hạn số ca mỗi người trong tuần, TUỲ CHỌN:
                None = không giới hạn; một số = áp dụng cho mọi người (ví dụ 5);
                dict {tên: số} = giới hạn riêng từng người (người không có trong dict thì không giới hạn)
    ca_kho    : list tên ca được coi là "khó" cần chia đều, ví dụ ["Tối"].
                None = ca cuối của ngày. [] = không dùng.
    trong_so  : dict ghi đè một phần TRONG_SO_MAC_DINH
    thoi_gian_toi_da : số giây tối đa cho solver
    cap_ca_cam : list các cặp ca KHÔNG được cùng một người làm trong cùng một ngày (luật cứng),
                 ví dụ [("Sáng", "Tối")]: ai làm ca Sáng thì hôm đó không làm ca Tối và ngược lại.
                 None = không cấm cặp nào.
    cap_ca_han_che : giống cap_ca_cam nhưng là LUẬT MỀM: máy cố tránh, chỉ xếp như vậy khi không còn
                 cách nào khác (mỗi lần vi phạm bị phạt, xem trọng số "cung_ngay").
    cap_ca_qua_dem : list các cặp (ca hôm trước, ca hôm sau) mà máy cố tránh cho cùng một người, ví dụ
                 [("Tối", "Sáng")] = làm ca Tối hôm nay rồi lại làm ca Sáng hôm sau. LUẬT MỀM, bí mới xếp
                 (trọng số "qua_dem"). None = tự dùng (ca cuối ngày, ca đầu ngày). [] = không dùng luật này.

    ghim      : dict {tên: {(ngày, ca), ...}} ca admin GHIM: người đó bắt buộc phải làm ca này
                (được phép dù họ chưa đăng ký ca đó)
    khong_xep : dict {tên: {(ngày, ca), ...}} ca người đó KHÔNG được xếp tuần này (ví dụ xin nghỉ đột xuất)
    full_time : list tên nhân viên full-time. Máy KHÔNG tự xếp họ: họ làm đúng các ca được liệt kê trong
                `ghim` (do admin xếp tay), không bị tính giới hạn, luật mềm hay chia đều.
                Các ca của họ vẫn được tính vào số người cần của từng ca.
    lich_su   : dict {tên: {"so_ca": n, "so_ca_kho": m}} số ca đã làm trong các tuần trước, để chia đều
                CÔNG BẰNG NHIỀU TUẦN (người làm nhiều hơn trước đó sẽ được ưu tiên nhẹ hơn). Chỉ là luật
                mềm: không cân bằng được thì máy vẫn xếp bình thường.

    Trả về dict:
      trang_thai : "OPTIMAL", "FEASIBLE", "INFEASIBLE", ...
      lich       : bảng lich[e][d][s] gồm 0/1 (None nếu không có lịch)
      các số liệu tóm tắt: so_ca, so_ca_kho, so_cap_lien_nhau, mong_muon_trung, mong_muon_tong
    """
    _kiem_tra_ten(nhan_vien, ngay, ca)
    N, D, S = len(nhan_vien), len(ngay), len(ca)
    tt = dict(TRONG_SO_MAC_DINH)
    tt.update(trong_so or {})

    if ca_kho is None:
        ca_kho = [ca[-1]] if S > 1 else []
    for c in ca_kho:
        if c not in ca:
            raise ValueError(f"Ca khó '{c}' không nằm trong danh sách ca")
    idx_kho = [ca.index(c) for c in ca_kho]
    cam = _cap_cam_chi_so(ca, cap_ca_cam)
    han_che = _cap_cam_chi_so(ca, cap_ca_han_che)
    qua_dem = _cap_qua_dem_chi_so(ca, cap_ca_qua_dem)

    need = _ma_tran_so_nguoi(ngay, ca, so_nguoi, so_nguoi_rieng)
    ok, bat_buoc, co_dinh = _chuan_bi_dang_ky(nhan_vien, ngay, ca, lam_duoc, ghim, khong_xep, full_time)
    gioi_han = _gioi_han_tuan(nhan_vien, toi_da_tuan)
    so_ca_cu, so_ca_kho_cu = _lich_su_so(nhan_vien, lich_su)
    muon = _ma_tran_theo_ten(nhan_vien, ngay, ca, mong_muon, False) if mong_muon else None

    model = cp_model.CpModel()
    x = {}
    for e in range(N):
        for d in range(D):
            for s in range(S):
                x[e, d, s] = model.NewBoolVar(f"x_{e}_{d}_{s}")

    # --- LUẬT CỨNG ---
    # 1) Mỗi ca đủ người
    for d in range(D):
        for s in range(S):
            model.Add(sum(x[e, d, s] for e in range(N)) == need[d][s])
    # 2) Chỉ xếp vào ca nhân viên làm được
    for e in range(N):
        for d in range(D):
            for s in range(S):
                if not ok[e][d][s]:
                    model.Add(x[e, d, s] == 0)
    # 2b) Ca được ghim (và ca cố định của nhân viên full-time) bắt buộc phải xếp
    for e in range(N):
        for d in range(D):
            for s in range(S):
                if bat_buoc[e][d][s]:
                    model.Add(x[e, d, s] == 1)
    # 3) Giới hạn số ca mỗi tuần (tuỳ chọn, không áp dụng cho full-time vì admin tự xếp)
    tong = []
    for e in range(N):
        t = sum(x[e, d, s] for d in range(D) for s in range(S))
        tong.append(t)
        if gioi_han[e] is not None and e not in co_dinh:
            model.Add(t <= gioi_han[e])

    # 4) Các cặp ca không được làm chung một ngày (ví dụ Sáng + Tối)
    for e in range(N):
        if e in co_dinh:
            continue                                       # admin tự xếp full-time, máy không áp luật này
        for d in range(D):
            for s1, s2 in cam:
                model.Add(x[e, d, s1] + x[e, d, s2] <= 1)

    # --- LUẬT MỀM (cộng dồn vào điểm phạt) ---
    phat = []
    so_ca_toi_da = D * S

    # a) Phạt các cặp ca liền nhau TRONG CÙNG MỘT NGÀY (ví dụ Sáng rồi Chiều, Chiều rồi Tối)
    cap_lien = []
    for e in range(N):
        if e in co_dinh:
            continue
        for d in range(D):
            for s in range(S - 1):
                y = model.NewBoolVar(f"lien_{e}_{d}_{s}")
                model.Add(x[e, d, s] + x[e, d, s + 1] - 1 <= y)
                cap_lien.append(y)
    phat.append(tt["lien_nhau"] * sum(cap_lien))

    # a1) Phạt ca qua đêm: làm ca cuối ngày hôm trước rồi ca đầu ngày hôm sau (ví dụ Tối rồi Sáng)
    cap_qua_dem = []
    for e in range(N):
        if e in co_dinh:
            continue
        for d in range(D - 1):
            for sa, sb in qua_dem:
                y = model.NewBoolVar(f"quadem_{e}_{d}_{sa}_{sb}")
                model.Add(x[e, d, sa] + x[e, d + 1, sb] - 1 <= y)
                cap_qua_dem.append(y)
    if cap_qua_dem:
        phat.append(tt["qua_dem"] * sum(cap_qua_dem))

    # a2) Phạt các cặp ca "hạn chế" làm chung một ngày (ví dụ Sáng + Tối)
    cung_ngay = []
    for e in range(N):
        if e in co_dinh:
            continue
        for d in range(D):
            for s1, s2 in han_che:
                y = model.NewBoolVar(f"cungngay_{e}_{d}_{s1}_{s2}")
                model.Add(x[e, d, s1] + x[e, d, s2] - 1 <= y)
                cung_ngay.append(y)
    if cung_ngay:
        phat.append(tt["cung_ngay"] * sum(cung_ngay))

    # b) Chia đều tổng số ca, TÍNH CẢ SỐ CA ĐÃ LÀM Ở CÁC TUẦN TRƯỚC (công bằng nhiều tuần).
    #    Full-time không tham gia chia đều vì admin tự xếp.
    nguoi_chia = [e for e in range(N) if e not in co_dinh]
    tong_kho = [sum(x[e, d, s] for d in range(D) for s in idx_kho) if idx_kho else 0 for e in range(N)]
    if len(nguoi_chia) >= 2:
        gioi = max(so_ca_cu + so_ca_kho_cu + [0]) + so_ca_toi_da
        cong_don = [so_ca_cu[e] + tong[e] for e in range(N)]
        nhieu = model.NewIntVar(0, gioi, "nhieu")
        it = model.NewIntVar(0, gioi, "it")
        model.AddMaxEquality(nhieu, [cong_don[e] for e in nguoi_chia])
        model.AddMinEquality(it, [cong_don[e] for e in nguoi_chia])
        phat.append(tt["deu_ca"] * (nhieu - it))

        # c) Chia đều các ca "khó" (cũng cộng dồn nhiều tuần)
        if idx_kho:
            kho_cong_don = [so_ca_kho_cu[e] + tong_kho[e] for e in range(N)]
            kho_nhieu = model.NewIntVar(0, gioi, "kho_nhieu")
            kho_it = model.NewIntVar(0, gioi, "kho_it")
            model.AddMaxEquality(kho_nhieu, [kho_cong_don[e] for e in nguoi_chia])
            model.AddMinEquality(kho_it, [kho_cong_don[e] for e in nguoi_chia])
            phat.append(tt["deu_ca_kho"] * (kho_nhieu - kho_it))

    # d) Thưởng cho ca mong muốn được xếp trúng
    o_mong_muon = []
    if muon is not None:
        o_mong_muon = [x[e, d, s] for e in range(N) if e not in co_dinh
                       for d in range(D) for s in range(S) if muon[e][d][s]]
        phat.append(-tt["mong_muon"] * sum(o_mong_muon))

    model.Minimize(sum(phat))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = thoi_gian_toi_da
    trang_thai = solver.Solve(model)
    ten_tt = solver.StatusName(trang_thai)

    ket_qua = {"trang_thai": ten_tt, "lich": None}
    if trang_thai in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        lich = [[[solver.Value(x[e, d, s]) for s in range(S)] for d in range(D)]
                for e in range(N)]
        ket_qua.update({
            "lich": lich,
            "diem_phat": solver.ObjectiveValue(),
            "so_ca": [sum(lich[e][d][s] for d in range(D) for s in range(S)) for e in range(N)],
            "so_ca_kho": [sum(lich[e][d][s] for d in range(D) for s in idx_kho) for e in range(N)],
            "so_cap_lien_nhau": sum(solver.Value(y) for y in cap_lien),
            "so_cap_cung_ngay": sum(solver.Value(y) for y in cung_ngay),
            "so_cap_qua_dem": sum(solver.Value(y) for y in cap_qua_dem),
            "mong_muon_trung": sum(solver.Value(v) for v in o_mong_muon),
            "mong_muon_tong": len(o_mong_muon),
        })
    return ket_qua


# ---------------------------------------------------------------
# Hàm hỗ trợ hiển thị và kiểm tra
# ---------------------------------------------------------------
def lich_theo_ca(lich, nhan_vien, ngay, ca):
    """Đổi lich[e][d][s] thành {(ngày, ca): [tên những người làm]} để dễ in/hiển thị."""
    return {
        (ngay[d], ca[s]): [nhan_vien[e] for e in range(len(nhan_vien)) if lich[e][d][s] == 1]
        for d in range(len(ngay)) for s in range(len(ca))
    }


def kiem_tra_du_lieu(nhan_vien, ngay, ca, so_nguoi, lam_duoc=None, so_nguoi_rieng=None,
                     ghim=None, khong_xep=None, full_time=None):
    """
    Kiểm tra TRƯỚC khi xếp: có ca nào mà số người làm được ít hơn số người cần không?
    Trả về danh sách cảnh báo (rỗng = dữ liệu ổn). Giúp admin biết cần sửa gì khi INFEASIBLE.
    """
    _kiem_tra_ten(nhan_vien, ngay, ca)
    need = _ma_tran_so_nguoi(ngay, ca, so_nguoi, so_nguoi_rieng)
    ok, bat_buoc, co_dinh = _chuan_bi_dang_ky(nhan_vien, ngay, ca, lam_duoc, ghim, khong_xep, full_time)
    canh_bao = []
    for d in range(len(ngay)):
        for s in range(len(ca)):
            co = sum(1 for e in range(len(nhan_vien)) if ok[e][d][s])
            da_ghim = sum(1 for e in range(len(nhan_vien)) if bat_buoc[e][d][s])
            if da_ghim > need[d][s]:
                canh_bao.append(f"{ngay[d]} - {ca[s]}: đã ghim/cố định {da_ghim} người nhưng ca chỉ cần {need[d][s]}")
            elif co < need[d][s]:
                canh_bao.append(f"{ngay[d]} - {ca[s]}: cần {need[d][s]} người nhưng chỉ có {co} người làm được")
    for e, ten in enumerate(nhan_vien):
        if not any(ok[e][d][s] for d in range(len(ngay)) for s in range(len(ca))):
            if e in co_dinh:
                canh_bao.append(f"{ten} (full-time): chưa được xếp ca nào")
            else:
                canh_bao.append(f"{ten}: chưa đăng ký ca nào")
    return canh_bao


def kiem_tra_lich(lich, nhan_vien, ngay, ca, so_nguoi, lam_duoc=None,
                  so_nguoi_rieng=None, toi_da_tuan=None, cap_ca_cam=None,
                  ghim=None, khong_xep=None, full_time=None):
    """
    Kiểm tra một lịch (kể cả lịch admin chỉnh tay) theo các LUẬT CỨNG.
    Trả về danh sách lỗi (rỗng = hợp lệ).
    """
    need = _ma_tran_so_nguoi(ngay, ca, so_nguoi, so_nguoi_rieng)
    ok, bat_buoc, co_dinh = _chuan_bi_dang_ky(nhan_vien, ngay, ca, lam_duoc, ghim, khong_xep, full_time)
    gioi_han = _gioi_han_tuan(nhan_vien, toi_da_tuan)
    cam = _cap_cam_chi_so(ca, cap_ca_cam)
    loi = []
    for d in range(len(ngay)):
        for s in range(len(ca)):
            n = sum(lich[e][d][s] for e in range(len(nhan_vien)))
            if n != need[d][s]:
                loi.append(f"{ngay[d]} - {ca[s]}: có {n} người, cần {need[d][s]}")
    for e in range(len(nhan_vien)):
        for d in range(len(ngay)):
            for s in range(len(ca)):
                if lich[e][d][s] == 1 and not ok[e][d][s]:
                    if e in co_dinh:
                        loi.append(f"{nhan_vien[e]} (full-time) bị xếp {ngay[d]} - {ca[s]} nhưng đó không phải ca cố định")
                    else:
                        loi.append(f"{nhan_vien[e]} không đăng ký {ngay[d]} - {ca[s]} nhưng bị xếp")
                if bat_buoc[e][d][s] and lich[e][d][s] != 1:
                    loi.append(f"{nhan_vien[e]} được ghim làm {ngay[d]} - {ca[s]} nhưng lịch không có ca này")
        if e in co_dinh:
            continue                                       # full-time do admin tự xếp, không áp các luật bên dưới
        for s1, s2 in cam:
            for d in range(len(ngay)):
                if lich[e][d][s1] == 1 and lich[e][d][s2] == 1:
                    loi.append(f"{nhan_vien[e]} làm cả ca {ca[s1]} và ca {ca[s2]} trong {ngay[d]}")
        if gioi_han[e] is not None:
            t = sum(lich[e][d][s] for d in range(len(ngay)) for s in range(len(ca)))
            if t > gioi_han[e]:
                loi.append(f"{nhan_vien[e]} làm {t} ca, vượt mức tối đa {gioi_han[e]}")
    return loi


def canh_bao_lien_nhau(lich, nhan_vien, ngay, ca):
    """Liệt kê các cặp ca liền nhau trong cùng một ngày (chỉ là cảnh báo cho admin biết, không phải lỗi)."""
    cb = []
    for e in range(len(nhan_vien)):
        for d in range(len(ngay)):
            for s in range(len(ca) - 1):
                if lich[e][d][s] == 1 and lich[e][d][s + 1] == 1:
                    cb.append(f"{nhan_vien[e]}: {ngay[d]} làm liền ca {ca[s]} và ca {ca[s + 1]}")
    return cb


def canh_bao_qua_dem(lich, nhan_vien, ngay, ca, cap_ca_qua_dem=None):
    """Liệt kê ai đang làm ca Tối hôm trước rồi ca Sáng hôm sau (hoặc cặp ca khác bạn chọn)."""
    cb = []
    for sa, sb in _cap_qua_dem_chi_so(ca, cap_ca_qua_dem):
        for e in range(len(nhan_vien)):
            for d in range(len(ngay) - 1):
                if lich[e][d][sa] == 1 and lich[e][d + 1][sb] == 1:
                    cb.append(f"{nhan_vien[e]}: ca {ca[sa]} {ngay[d]} rồi ca {ca[sb]} {ngay[d + 1]}")
    return cb


def canh_bao_cung_ngay(lich, nhan_vien, ngay, ca, cap_ca_han_che):
    """Liệt kê những người đang làm cả hai ca trong một cặp "hạn chế" cùng một ngày (chỉ là cảnh báo)."""
    cb = []
    for s1, s2 in _cap_cam_chi_so(ca, cap_ca_han_che):
        for e in range(len(nhan_vien)):
            for d in range(len(ngay)):
                if lich[e][d][s1] == 1 and lich[e][d][s2] == 1:
                    cb.append(f"{nhan_vien[e]}: {ngay[d]} làm cả ca {ca[s1]} và ca {ca[s2]}")
    return cb


# ---------------------------------------------------------------
# Chẩn đoán khi không xếp được, và xếp lại sau khi admin đồng ý nới luật
# ---------------------------------------------------------------
def _xep_duoc(nhan_vien, ngay, ca, so_nguoi, **tuy_chon):
    """Thử xếp nhanh (tối đa 5 giây), trả về True nếu tìm được lịch."""
    tuy_chon["thoi_gian_toi_da"] = 5
    return xep_lich(nhan_vien, ngay, ca, so_nguoi, **tuy_chon)["lich"] is not None


def chan_doan(nhan_vien, ngay, ca, so_nguoi, lam_duoc=None, so_nguoi_rieng=None,
              toi_da_tuan=None, cap_ca_cam=None, ghim=None, khong_xep=None, full_time=None, **khac):
    """
    Giải thích VÌ SAO không xếp được. Trả về danh sách các vấn đề, mỗi vấn đề là dict:
      {"loai": "thieu_nguoi" | "ghim_qua_nhieu" | "cap_ca" | "gioi_han_tuan" | "mau_thuan", "noi_dung": "câu giải thích"}
    Danh sách rỗng nghĩa là không tìm ra vấn đề nào.
    """
    _kiem_tra_ten(nhan_vien, ngay, ca)
    need = _ma_tran_so_nguoi(ngay, ca, so_nguoi, so_nguoi_rieng)
    ok, bat_buoc, co_dinh = _chuan_bi_dang_ky(nhan_vien, ngay, ca, lam_duoc, ghim, khong_xep, full_time)
    gioi_han = _gioi_han_tuan(nhan_vien, toi_da_tuan)
    cam = _cap_cam_chi_so(ca, cap_ca_cam)
    N, D, S = len(nhan_vien), len(ngay), len(ca)
    van_de = []

    # 1) Ca nào ghim quá nhiều người, hoặc có ít người đăng ký hơn số người cần
    for d in range(D):
        for s in range(S):
            da_ghim = sum(1 for e in range(N) if bat_buoc[e][d][s])
            co = sum(1 for e in range(N) if ok[e][d][s])
            if da_ghim > need[d][s]:
                van_de.append({"loai": "ghim_qua_nhieu", "noi_dung":
                    f"{ngay[d]} - {ca[s]}: đã ghim/cố định {da_ghim} người nhưng ca chỉ cần {need[d][s]}"})
            elif co < need[d][s]:
                van_de.append({"loai": "thieu_nguoi", "noi_dung":
                    f"{ngay[d]} - {ca[s]}: cần {need[d][s]} người nhưng chỉ có {co} người đăng ký"})

    # 2) Luật cứng "một người không làm cả hai ca trong một ngày": có đủ người khác nhau không?
    #    (chỉ xét nhân viên máy tự xếp; trừ đi những người full-time đã cố định ở ca đó)
    tu_do = [e for e in range(N) if e not in co_dinh]
    for s1, s2 in cam:
        for d in range(D):
            n1 = need[d][s1] - sum(1 for e in co_dinh if bat_buoc[e][d][s1])
            n2 = need[d][s2] - sum(1 for e in co_dinh if bat_buoc[e][d][s2])
            nhom1 = {e for e in tu_do if ok[e][d][s1]}
            nhom2 = {e for e in tu_do if ok[e][d][s2]}
            if len(nhom1) >= n1 and len(nhom2) >= n2 and len(nhom1 | nhom2) < n1 + n2:
                van_de.append({"loai": "cap_ca", "noi_dung":
                    f"{ngay[d]}: ca {ca[s1]} cần {n1} người và ca {ca[s2]} cần {n2} người (chưa tính full-time), "
                    f"nhưng chỉ có {len(nhom1 | nhom2)} người đăng ký hai ca này, "
                    f"mà luật không cho một người làm cả hai ca trong một ngày"})

    # 3) Giới hạn số ca mỗi tuần: tổng khả năng có đủ cho tổng nhu cầu không?
    if any(g is not None for g in gioi_han):
        tong_can = sum(need[d][s] for d in range(D) for s in range(S))
        tong_co = 0
        for e in range(N):
            so_o = sum(1 for d in range(D) for s in range(S) if ok[e][d][s])
            tong_co += so_o if (e in co_dinh or gioi_han[e] is None) else min(gioi_han[e], so_o)
        if tong_co < tong_can:
            van_de.append({"loai": "gioi_han_tuan", "noi_dung":
                f"Cả tuần cần {tong_can} lượt làm, nhưng với giới hạn số ca mỗi người "
                f"thì các nhân viên chỉ đáp ứng được tối đa {tong_co} lượt"})
        for e in tu_do:
            so_ghim = sum(1 for d in range(D) for s in range(S) if bat_buoc[e][d][s])
            if gioi_han[e] is not None and so_ghim > gioi_han[e]:
                van_de.append({"loai": "gioi_han_tuan", "noi_dung":
                    f"{nhan_vien[e]}: đã ghim {so_ghim} ca nhưng giới hạn chỉ {gioi_han[e]} ca/tuần"})

    # 4) Chưa tìm ra lý do rõ ràng: thử bỏ từng luật xem luật nào gây ra
    if not van_de:
        co_so = dict(lam_duoc=lam_duoc, so_nguoi_rieng=so_nguoi_rieng, toi_da_tuan=toi_da_tuan,
                     cap_ca_cam=cap_ca_cam, ghim=ghim, khong_xep=khong_xep, full_time=full_time)
        thu = []
        if cap_ca_cam:
            thu.append(("cap_ca", "luật không cho một người làm hai ca trong một ngày", {"cap_ca_cam": None}))
        if any(g is not None for g in gioi_han):
            thu.append(("gioi_han_tuan", "giới hạn số ca mỗi tuần", {"toi_da_tuan": None}))
        if khong_xep:
            thu.append(("mau_thuan", "các ca đã chặn không xếp", {"khong_xep": None}))
        if ghim and not full_time:
            thu.append(("ghim_qua_nhieu", "các ca đã ghim", {"ghim": None}))
        for loai, ten, bo in thu:
            if _xep_duoc(nhan_vien, ngay, ca, so_nguoi, **{**co_so, **bo}):
                van_de.append({"loai": loai, "noi_dung": f"Chỉ cần nới {ten} là xếp được"})
        if not van_de:
            van_de.append({"loai": "mau_thuan", "noi_dung":
                "Các luật kết hợp lại với nhau gây mâu thuẫn, chưa chỉ ra được một ca hay một luật cụ thể"})
    return van_de


def xep_lich_tu_van(nhan_vien, ngay, ca, so_nguoi, hoi=None, **tuy_chon):
    """
    Xếp lịch; nếu không xếp được thì chẩn đoán và (nếu nới luật giúp được) HỎI admin.

    hoi : hàm nhận danh sách vấn đề (kết quả của chan_doan) và trả về True/False.
          True nghĩa là admin đồng ý cho một người làm hai ca trong một ngày
          (các cặp ca trong cap_ca_cam được chuyển thành luật mềm).
          Giao diện nào cũng tự viết hàm này (notebook dùng input(), web dùng nút bấm).
          Solver không tự hỏi, nên file này vẫn không có input().

    Trả về dict:
      ket_qua         : kết quả của xep_lich (lần xếp cuối cùng)
      van_de          : danh sách vấn đề đã chẩn đoán (rỗng nếu xếp được ngay)
      da_noi_long     : True nếu lịch cuối cùng có được nhờ admin đồng ý nới luật
      nguoi_lam_hai_ca: danh sách ai bị xếp làm hai ca cùng ngày sau khi nới luật
    """
    kq = xep_lich(nhan_vien, ngay, ca, so_nguoi, **tuy_chon)
    ket = {"ket_qua": kq, "van_de": [], "da_noi_long": False, "nguoi_lam_hai_ca": []}
    if kq["lich"] is not None:
        return ket

    van_de = chan_doan(nhan_vien, ngay, ca, so_nguoi, **tuy_chon)
    ket["van_de"] = van_de

    cap_cung = tuy_chon.get("cap_ca_cam")
    if not cap_cung or hoi is None:
        return ket

    # Thử nới luật: chuyển luật cứng thành luật mềm. Chỉ hỏi admin khi nới thật sự giúp được.
    tuy_chon_noi = dict(tuy_chon)
    tuy_chon_noi["cap_ca_cam"] = None
    tuy_chon_noi["cap_ca_han_che"] = list(tuy_chon.get("cap_ca_han_che") or []) + list(cap_cung)
    kq_noi = xep_lich(nhan_vien, ngay, ca, so_nguoi, **tuy_chon_noi)
    if kq_noi["lich"] is None:
        return ket          # dù nới cũng không xếp được, cần sửa dữ liệu, không hỏi vô ích

    if hoi(van_de):
        ket["ket_qua"] = kq_noi
        ket["da_noi_long"] = True
        ket["nguoi_lam_hai_ca"] = canh_bao_cung_ngay(kq_noi["lich"], nhan_vien, ngay, ca, cap_cung)
    return ket
