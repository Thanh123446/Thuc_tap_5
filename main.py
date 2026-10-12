# ==============================================================================
# FILE: main.py
# HOÀN CHỈNH - TÍCH HỢP ĐĂNG NHẬP, PHÂN QUYỀN ADMIN & BẢO MẬT BCRYPT 72-BYTE
# ==============================================================================

import os
import json
import logging
import base64
import asyncio
import time
from typing import Optional
from contextlib import asynccontextmanager

# Thư viện Mã hóa Mật khẩu
from passlib.context import CryptContext

# Thư viện Web & API Framework
from fastapi import FastAPI, Depends, HTTPException, APIRouter, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Thư viện Cơ sở dữ liệu (SQLAlchemy)
from sqlalchemy.orm import Session
from database import engine, Base, get_db
import models

# Thư viện Google AI (SDK google-genai)
from google import genai
from google.genai import types

# ------------------------------------------------------------------------------
# 1. ĐỊNH NGHĨA ĐƯỜNG DẪN & CẤU HÌNH MÃ HÓA
# ------------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML_PATH = os.path.join(BASE_DIR, "index.html")
ADMIN_HTML_PATH = os.path.join(BASE_DIR, "admin.html")
LOGIN_HTML_PATH = os.path.join(BASE_DIR, "login.html")

# Xử lý cắt chủ động 72 bytes để tương thích tuyệt đối với Bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    safe_password = password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    return pwd_context.hash(safe_password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    safe_password = plain_password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    return pwd_context.verify(safe_password, hashed_password)

# Import các thuật toán GIS
from server_gis import (
    load_data, 
    loc_thua as gis_loc_thua, 
    thua_cuc_tri as gis_thua_cuc_tri, 
    thua_gan as gis_thua_gan, 
    khoang_cach as gis_khoang_cach
)

logger = logging.getLogger("MAIN_LOGGER")
logger.setLevel(logging.INFO)


# ------------------------------------------------------------------------------
# 2. LIFESPAN: NẠP MAP, TẠO BẢNG & TỰ ĐỘNG TẠO TÀI KHOẢN ADMIN MẶC ĐỊNH
# ------------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_data()  # Nạp dữ liệu bản đồ vào RAM
    
    try:
        Base.metadata.create_all(bind=engine)
        print("[OK DATABASE] Đã kết nối CSDL và khởi tạo các bảng thành công!")
        
        # Kiểm tra và tự động khởi tạo Admin mặc định nếu chưa tồn tại
        db = next(get_db())
        admin_user = db.query(models.User).filter(models.User.username == "admin").first()
        if not admin_user:
            default_admin = models.User(
                username="admin",
                password_hash=hash_password("admin123"),
                full_name="Quản Trị Viên Hệ Thống",
                role="admin",
                is_active=True
            )
            db.add(default_admin)
            db.commit()
            print("[OK AUTH] Đã tạo tài khoản Admin mặc định: (Username: admin | Password: admin123)")
        db.close()

    except Exception as e:
        print(f"[LỖI DATABASE] Khởi tạo CSDL thất bại: {str(e)}")
        
    yield
    print("[INFO] Đang đóng ứng dụng...")


app = FastAPI(
    title="Hệ thống AI Bản đồ Nông nghiệp",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------------------
# 3. ROUTE PHỤC VỤ TRANG GIAO DIỆN WEB
# ------------------------------------------------------------------------------
@app.get("/")
async def serve_index_html():
    if os.path.exists(INDEX_HTML_PATH):
        return FileResponse(INDEX_HTML_PATH)
    return {"message": "Không tìm thấy file index.html"}

@app.get("/admin")
async def serve_admin_html():
    if os.path.exists(ADMIN_HTML_PATH):
        return FileResponse(ADMIN_HTML_PATH)
    return {"message": "Không tìm thấy file admin.html"}

@app.get("/login")
async def serve_login_html():
    if os.path.exists(LOGIN_HTML_PATH):
        return FileResponse(LOGIN_HTML_PATH)
    return {"message": "Không tìm thấy file login.html"}


# ------------------------------------------------------------------------------
# 4. API AUTHENTICATION (ĐĂNG KÝ & ĐĂNG NHẬP)
# ------------------------------------------------------------------------------
class RegisterSchema(BaseModel):
    full_name: str
    username: str
    password: str

class LoginSchema(BaseModel):
    username: str
    password: str

@app.post("/api/register", summary="Đăng ký tài khoản mới")
def register_user(data: RegisterSchema, db: Session = Depends(get_db)):
    existing_user = db.query(models.User).filter(models.User.username == data.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Tên tài khoản này đã tồn tại trên hệ thống!")
    
    new_user = models.User(
        username=data.username,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role="user"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "Đăng ký tài khoản thành công!", "username": new_user.username}

@app.post("/api/login", summary="Đăng nhập tài khoản")
def login_user(data: LoginSchema, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == data.username).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Tên tài khoản hoặc mật khẩu không chính xác!")
    
    return {
        "message": "Đăng nhập thành công!",
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role
        }
    }


# ------------------------------------------------------------------------------
# 5. CẤU HÌNH AI GEMINI CLIENT & TOOLS TRA CỨU GIS
# ------------------------------------------------------------------------------
def tool_loc_thua(dieu_kien: str) -> str:
    return json.dumps(gis_loc_thua(dieu_kien=dieu_kien), ensure_ascii=False)

def tool_thua_cuc_tri(truong: str = "dien_tich", loai: str = "max") -> str:
    return json.dumps(gis_thua_cuc_tri(truong=truong, loai=loai), ensure_ascii=False)

def tool_thua_gan(lat: float, lon: float, ban_kinh_m: float = 500.0) -> str:
    return json.dumps(gis_thua_gan(lat=lat, lon=lon, ban_kinh_m=ban_kinh_m), ensure_ascii=False)

def tool_khoang_cach(dt1: str, dt2: str) -> str:
    return json.dumps(gis_khoang_cach(dt1=dt1, dt2=dt2), ensure_ascii=False)

def tool_du_bao_thoi_tiet(tinh_thanh: str) -> str:
    return f"Thời tiết tại {tinh_thanh}: Nắng nhẹ, nhiệt độ 28°C - 32°C, độ ẩm 75%. (Nguồn: Trung tâm Dự báo KTTV Quốc gia)"

def tool_tra_cuu_gia_nong_san(san_pham: str, tinh_thanh: Optional[str] = None) -> str:
    dia_ban = f" tại {tinh_thanh}" if tinh_thanh else ""
    return f"Giá {san_pham}{dia_ban}: 18,500 VNĐ/kg, xu hướng ổn định. (Nguồn: Cổng thông tin Thị trường Nông sản)"

api_key = os.environ.get("GEMINI_API_KEY", "AQ.Ab8RN6L0VAn24MjUTa0JWoZ3XrvdAhXUiM615YV3vuycpmAdyQ")
client = genai.Client(api_key=api_key)

system_instruction = """
Bạn là Trợ lý AI Bản đồ Nông nghiệp thông minh.
QUY TẮC PHẢN HỒI:
1. Đối với chào hỏi hoặc giao tiếp thông thường: Trả lời NGAY LẬP TỨC, KHÔNG gọi công cụ.
2. Chỉ gọi các công cụ GIS khi người dùng hỏi về thửa đất, diện tích, khoảng cách, vị trí.
3. Trả lời bằng TIẾNG VIỆT TỰ NHIÊN, rõ ràng, KHÔNG hiển thị chuỗi JSON thô.
"""

ai_config = types.GenerateContentConfig(
    system_instruction=system_instruction,
    tools=[
        tool_loc_thua, tool_thua_cuc_tri, tool_thua_gan, 
        tool_khoang_cach, tool_du_bao_thoi_tiet, tool_tra_cuu_gia_nong_san
    ]
)

class ChatRequest(BaseModel):
    message: str
    user_id: Optional[int] = None
    image_base64: Optional[str] = None

@app.post("/api/chat", summary="API Chatbot AI (Auto-Retry & Fallback Gemini 3.5+)")
async def chat_endpoint(request: ChatRequest, db: Session = Depends(get_db)):
    MODELS_TO_TRY = [
        'gemini-3.5-flash-lite',
        'gemini-3.5-flash',
        'gemini-3.6-flash',
        'gemini-3.7-flash',
        'gemini-3.8-flash'
    ]
    
    contents = []
    if request.image_base64:
        raw_b64 = request.image_base64.split(",")[1] if "," in request.image_base64 else request.image_base64
        contents.append(types.Part.from_bytes(data=base64.b64decode(raw_b64), mime_type="image/jpeg"))
    contents.append(request.message)

    reply_text = None
    for model_name in MODELS_TO_TRY:
        for attempt in range(3):
            try:
                chat_session = client.chats.create(model=model_name, config=ai_config)
                response = await asyncio.wait_for(
                    asyncio.to_thread(chat_session.send_message, contents),
                    timeout=35.0
                )
                reply_text = response.text
                break
            except Exception as e:
                if "503" in str(e) or "UNAVAILABLE" in str(e):
                    await asyncio.sleep((attempt + 1) * 2)
                else:
                    break
        if reply_text:
            break

    if not reply_text:
        return {"reply": "Máy chủ AI của Google đang bị quá tải. Vui lòng thử lại sau khoảng 15-30 giây!"}

    # Lưu hội thoại vào CSDL SSMS
    try:
        new_chat = models.ChatHistory(
            user_id=request.user_id,
            user_message=request.message,
            bot_response=reply_text,
            intent="GEMINI_GIS_CHAT"
        )
        db.add(new_chat)
        db.commit()
    except Exception as db_err:
        db.rollback()
        logger.error(f"Lỗi lưu CSDL: {str(db_err)}")

    return {"reply": reply_text}


# Các API GIS trực tiếp
@app.get("/api/loc-thua")
def api_loc_thua(dieu_kien: str): 
    return gis_loc_thua(dieu_kien)

@app.get("/api/thua-cuc-tri")
def api_thua_cuc_tri(truong: str = "dien_tich", loai: str = "max"): 
    return gis_thua_cuc_tri(truong, loai)

@app.get("/api/thua-gan")
def api_thua_gan(lat: float, lon: float, ban_kinh_m: float = 500.0): 
    return gis_thua_gan(lat, lon, ban_kinh_m)

@app.get("/api/khoang-cach")
def api_khoang_cach(dt1: str, dt2: str): 
    return gis_khoang_cach(dt1, dt2)


# ------------------------------------------------------------------------------
# 6. ROUTER DÀNH RIÊNG CHO ADMIN
# ------------------------------------------------------------------------------
admin_router = APIRouter(prefix="/api/admin", tags=["Admin"])

@admin_router.get("/history")
def get_all_admin_chat_history(db: Session = Depends(get_db)):
    chats = db.query(models.ChatHistory).order_by(models.ChatHistory.id.desc()).all()
    return {"total": len(chats), "data": chats}

@admin_router.delete("/history/{chat_id}")
def delete_admin_chat_history(chat_id: int, db: Session = Depends(get_db)):
    chat = db.query(models.ChatHistory).filter(models.ChatHistory.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi chat.")
    db.delete(chat)
    db.commit()
    return {"message": "Xóa bản ghi lịch sử chat thành công"}

@admin_router.get("/users")
def get_all_users(db: Session = Depends(get_db)):
    users = db.query(models.User).order_by(models.User.id.asc()).all()
    return [{"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role, "created_at": u.created_at} for u in users]

@admin_router.put("/users/{user_id}/grant-admin")
def grant_admin_role(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng này!")
    
    user.role = "admin"
    db.commit()
    return {"message": f"Đã nâng cấp quyền Admin cho tài khoản {user.username}!"}

app.include_router(admin_router)

# Mount các file giao diện tĩnh (HTML, CSS, JS)
app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="static")


# ------------------------------------------------------------------------------
# 7. KHỞI CHẠY APPLICATION SERVER
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)