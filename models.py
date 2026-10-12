from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

# Bảng 1: Lưu thông tin tài khoản và phân quyền (Admin / User)
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)  # Tên đăng nhập
    password_hash = Column(String(255), nullable=False)                      # Mật khẩu đã mã hóa
    full_name = Column(String(100), nullable=True)                           # Họ và tên
    role = Column(String(20), default="user", nullable=False)                # Vai trò: "admin" hoặc "user"
    is_active = Column(Boolean, default=True)                                # Trạng thái hoạt động
    created_at = Column(DateTime, default=datetime.utcnow)

    # Quan hệ liên kết tới lịch sử chat và nhật ký
    chat_histories = relationship("ChatHistory", back_populates="user")
    crop_logs = relationship("CropLog", back_populates="user")


# Bảng 2: Lưu lịch sử trò chuyện Chatbot
class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)         # ID người dùng (để trống nếu chat vô danh)
    user_message = Column(Text, nullable=False)                               # Câu hỏi người dùng
    bot_response = Column(Text, nullable=False)                               # AI trả lời
    intent = Column(String(100), nullable=True)                               # Ý định AI phân tích
    created_at = Column(DateTime, default=datetime.utcnow)

    # Liên kết ngược lại bảng User
    user = relationship("User", back_populates="chat_histories")


# Bảng 3: Lưu nhật ký ghi chú nông nghiệp
class CropLog(Base):
    __tablename__ = "crop_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)         # ID người tạo ghi chú
    so_thua = Column(String(50), index=True)                                  # Mã/số thửa đất
    ten_cay_trong = Column(String(100))                                       # Tên cây trồng
    ghi_chu = Column(Text, nullable=True)                                      # Ghi chú tình trạng
    ngay_tao = Column(DateTime, default=datetime.utcnow)

    # Liên kết ngược lại bảng User
    user = relationship("User", back_populates="crop_logs")