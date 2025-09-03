from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    
    # 設定
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
    
    # データベース設定（本番環境では環境変数から取得）
    database_url = os.environ.get('DATABASE_URL') or os.environ.get('DATABASE_PUBLIC_URL', 'sqlite:///inventory.db')
    
    # PostgreSQLのURLを修正
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    # 本番環境ではPostgreSQLのみ使用（SQLiteを完全に無効化）
    if os.environ.get('RAILWAY_ENVIRONMENT'):
        if not database_url.startswith('postgresql://'):
            # デバッグ情報を出力
            print(f"DEBUG: DATABASE_URL = {os.environ.get('DATABASE_URL')}")
            print(f"DEBUG: DATABASE_PUBLIC_URL = {os.environ.get('DATABASE_PUBLIC_URL')}")
            print(f"DEBUG: Final database_url = {database_url}")
            raise ValueError("PostgreSQL database is required in Railway environment. Please add a PostgreSQL database to your Railway project.")
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # CORS設定
    CORS(app)
    
    # データベース初期化
    db.init_app(app)
    
    # ブループリントの登録
    from app.controllers.inventory_controller import inventory_bp
    app.register_blueprint(inventory_bp)
    
    # データベーステーブルの作成
    with app.app_context():
        db.create_all()
        
        # 必要なディレクトリの作成
        os.makedirs('uploads', exist_ok=True)
        os.makedirs('reports', exist_ok=True)
        os.makedirs('models', exist_ok=True)
    
    return app
