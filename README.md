# Ứng dụng xếp lịch làm tự động

Ứng dụng web giúp cửa hàng, nhà hàng xếp lịch làm theo ca cho nhân viên. Nhân viên tự đăng ký những ca làm được, quản lý bấm một nút để máy xếp lịch, thay vì ngồi xếp tay hàng giờ.

## Tính năng
- Cấu hình linh hoạt: số ca, tên ca, giờ bắt đầu/kết thúc, số người mỗi ca
- Nhân viên part-time đăng ký ca theo từng tuần; nhân viên full-time do quản lý ghim lịch cố định
- Máy tự xếp bằng Google OR-Tools (CP-SAT): luật cứng (đủ người, đúng ca đã đăng ký, giới hạn ca/tuần tùy chọn) và luật mềm (tránh ca liền nhau, ca qua đêm, chia đều số ca và ca khó, công bằng nhiều tuần)
- Khi không xếp được: chỉ ra ca nào thiếu người, hỏi quản lý có nới luật không
- Ghim ca / chặn ca bằng tay, sửa tay từng ô và báo vi phạm ngay
- Lưu lịch sử, thống kê số ca và số giờ theo tuần/tháng, xuất Excel
- Đăng nhập, phân quyền quản lý / nhân viên (mật khẩu được băm, khóa tạm khi nhập sai nhiều lần)

## Công nghệ
Python, OR-Tools CP-SAT, SQLite, Streamlit, pytest.

## Cài đặt và chạy
```
pip install -r requirements.txt
streamlit run app.py
```
Lần đầu mở, app sẽ yêu cầu tạo tài khoản quản lý. Dữ liệu lưu trong file `cua_hang.db` 

## Chạy kiểm thử
```
pip install -r requirements-dev.txt
pytest
```

## Cấu trúc
- `solver.py`: mô hình xếp lịch và chẩn đoán lỗi
- `database.py`: lưu trữ SQLite
- `auth.py`: đăng nhập và phân quyền
- `app.py`: giao diện Streamlit
- `test_*.py`: kiểm thử tự động
- `thu_*.ipynb`: notebook thử nghiệm với dữ liệu mẫu
