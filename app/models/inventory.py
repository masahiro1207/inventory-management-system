from app import db
from datetime import datetime

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_code = db.Column(db.String(50), unique=True, nullable=False)
    category = db.Column(db.String(100))
    manufacturer = db.Column(db.String(100), nullable=False)
    product_name = db.Column(db.String(200), nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    min_quantity = db.Column(db.Integer, default=0)
    current_stock = db.Column(db.Integer, default=0)
    dealer = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    aliases = db.relationship(
        'ProductAlias',
        backref='product',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )

    def __repr__(self):
        return f'<Product {self.product_name}>'


class ProductAlias(db.Model):
    """取込時の正式名称など。表示は Product.product_name（手動編集名）を優先。"""
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(
        db.Integer, db.ForeignKey('product.id', ondelete='CASCADE'), nullable=False
    )
    alias_name = db.Column(db.String(200), nullable=False)
    source = db.Column(db.String(50))  # pdf, csv, rename, manual
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('product_id', 'alias_name', name='uq_product_alias_name'),
    )

    def __repr__(self):
        return f'<ProductAlias {self.alias_name} -> {self.product_id}>'


class OrderHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    dealer = db.Column(db.String(100))
    
    product = db.relationship('Product', backref='order_history')

    def __repr__(self):
        return f'<OrderHistory {self.product.product_name} - {self.quantity}>'
