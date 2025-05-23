# Cоздать сервис,
# который забирает данные по API, сохраняет их в базу данных
# и реализует API интерфейс для работы с данными в базе,
# используя FastAIP и SQLAlchemy для работы с базой.

import os
import json
import re
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi_redis_cache import FastApiRedisCache, cache
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, func
from sqlalchemy.orm import sessionmaker, Session, declarative_base
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SellerBase(BaseModel):
    name: str
    email: str = Field(..., pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

    @field_validator('email')
    def validate_email(cls, v):
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", v):
            raise ValueError("Invalid email format")
        return v

class SellerCreate(SellerBase):
    pass

class Seller(SellerBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class ProductBase(BaseModel):
    name: str
    price: float
    seller_id: int

class ProductCreate(ProductBase):
    pass

class Product(ProductBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class SaleBase(BaseModel):
    product_id: int
    quantity: int
    sale_date: datetime

class SaleCreate(SaleBase):
    pass

class Sale(SaleBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class StatisticsRequest(BaseModel):
    email: str = Field(..., pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sql_app.db")
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class DBSeller(Base):
    __tablename__ = "sellers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)

class DBProduct(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    price = Column(Float)
    seller_id = Column(Integer, index=True)

class DBSale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, index=True)
    quantity = Column(Integer)
    sale_date = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_cache = FastApiRedisCache()
    redis_cache.init(
        host_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
        prefix="myapi-cache",
        response_header="X-MyAPI-Cache",
        ignore_arg_types=[BackgroundTasks]
    )
    yield

app = FastAPI(lifespan=lifespan)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def send_email(to_email: str, subject: str, body: str):
    smtp_server = os.getenv("SMTP_SERVER", "smtp.example.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_username = os.getenv("SMTP_USERNAME", "user@example.com")
    smtp_password = os.getenv("SMTP_PASSWORD", "password")

    msg = MIMEMultipart()
    msg["From"] = smtp_username
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)
        server.quit()
        logger.info(f"Email sent to {to_email}")
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {str(e)}")
        raise

def gather_statistics(db: Session):
    sellers_stats = []
    sellers = db.query(DBSeller).all()

    for seller in sellers:
        products_count = db.query(DBProduct).filter(DBProduct.seller_id == seller.id).count()

        sales_count = db.query(DBSale) \
            .join(DBProduct, DBSale.product_id == DBProduct.id) \
            .filter(DBProduct.seller_id == seller.id) \
            .count()

        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        shipments_count = db.query(DBSale) \
            .join(DBProduct, DBSale.product_id == DBProduct.id) \
            .filter(DBProduct.seller_id == seller.id) \
            .filter(DBSale.sale_date >= month_start) \
            .count()

        sellers_stats.append({
            "seller_id": seller.id,
            "seller_name": seller.name,
            "products_count": products_count,
            "sales_count": sales_count,
            "shipments_count": shipments_count
        })

    return sellers_stats

def generate_statistics_report(stats: List[dict]) -> str:
    report_lines = ["Статистика по продавцам", "=" * 30, ""]

    for stat in stats:
        report_lines.extend([
            f"Продавец: {stat['seller_name']} (ID: {stat['seller_id']})",
            f"- Количество товаров: {stat['products_count']}",
            f"- Общее количество продаж: {stat['sales_count']}",
            f"- Количество отгрузок за текущий месяц: {stat['shipments_count']}",
            ""
        ])

    report_lines.append(f"Отчет сгенерирован: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(report_lines)

def send_statistics_email(email: str, db: Session):
    try:
        stats = gather_statistics(db)
        report = generate_statistics_report(stats)
        send_email(
            to_email=email,
            subject="Статистика продавцов",
            body=report
        )
    except Exception as e:
        logger.error(f"Error in background task: {str(e)}")
        raise

@app.post("/sellers/", response_model=Seller)
@cache(expire=60)
def create_seller(seller: SellerCreate, db: Session = Depends(get_db)):
    db_seller = DBSeller(**seller.model_dump())
    db.add(db_seller)
    db.commit()
    db.refresh(db_seller)
    return db_seller

@app.get("/sellers/", response_model=List[Seller])
@cache(expire=30)
def read_sellers(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    sellers = db.query(DBSeller).offset(skip).limit(limit).all()
    return sellers

@app.get("/sellers/{seller_id}", response_model=Seller)
@cache(expire=30)
def read_seller(seller_id: int, db: Session = Depends(get_db)):
    seller = db.query(DBSeller).filter(DBSeller.id == seller_id).first()
    if seller is None:
        raise HTTPException(status_code=404, detail="Seller not found")
    return seller

@app.post("/products/", response_model=Product)
@cache(expire=60)
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    db_product = DBProduct(**product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

@app.get("/products/", response_model=List[Product])
@cache(expire=30)
def read_products(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    products = db.query(DBProduct).offset(skip).limit(limit).all()
    return products

@app.get("/products/{product_id}", response_model=Product)
@cache(expire=30)
def read_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(DBProduct).filter(DBProduct.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@app.post("/sales/", response_model=Sale)
@cache(expire=60)
def create_sale(sale: SaleCreate, db: Session = Depends(get_db)):
    db_sale = DBSale(**sale.model_dump())
    db.add(db_sale)
    db.commit()
    db.refresh(db_sale)
    return db_sale

@app.get("/sales/", response_model=List[Sale])
@cache(expire=30)
def read_sales(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    sales = db.query(DBSale).offset(skip).limit(limit).all()
    return sales

@app.get("/sales/{sale_id}", response_model=Sale)
@cache(expire=30)
def read_sale(sale_id: int, db: Session = Depends(get_db)):
    sale = db.query(DBSale).filter(DBSale.id == sale_id).first()
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found")
    return sale

@app.post("/statistics/")
def send_statistics_report(
        request: StatisticsRequest,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db)
):
    background_tasks.add_task(send_statistics_email, request.email, db)
    return {"message": "Запрос на генерацию отчета принят. Отчет будет отправлен на указанный email."}