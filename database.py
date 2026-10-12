import urllib.parse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 1. Server Name và Database Name
SERVER_NAME = r"DESKTOP-KNP80BR\MSSQLSERVER01"
DATABASE_NAME = "AgricultureDB"

# 2. Tạo chuỗi kết nối ODBC an toàn (Mã hóa tự động các ký tự đặc biệt như '\' và khoảng trắng)
params = urllib.parse.quote_plus(
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={SERVER_NAME};"
    f"DATABASE={DATABASE_NAME};"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

DATABASE_URL = f"mssql+pyodbc:///?odbc_connect={params}"

# 3. Khởi tạo Engine và Session
engine = create_engine(DATABASE_URL, echo=True) # echo=True để in log SQL ra terminal kiểm tra
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()