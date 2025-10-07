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
    
    # PostgreSQLのURLを修正（HerokuやRailwayの古いURLフォーマット対応）
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    # 本番環境の検証（Railway環境の場合）
    if os.environ.get('RAILWAY_ENVIRONMENT'):
        # デバッグ情報を出力
        print(f"DEBUG: RAILWAY_ENVIRONMENT = {os.environ.get('RAILWAY_ENVIRONMENT')}")
        print(f"DEBUG: DATABASE_URL = {os.environ.get('DATABASE_URL')}")
        print(f"DEBUG: DATABASE_PUBLIC_URL = {os.environ.get('DATABASE_PUBLIC_URL')}")
        print(f"DEBUG: Final database_url = {database_url}")
        
        # PostgreSQLが推奨だが、SQLiteでも動作可能にする
        if not database_url.startswith('postgresql://'):
            print("WARNING: Using SQLite on Railway - PostgreSQL is recommended for production!")
            # SQLiteの場合、データディレクトリを確実に作成
            if database_url.startswith('sqlite'):
                db_dir = os.path.dirname(database_url.replace('sqlite:///', ''))
                if db_dir:
                    os.makedirs(db_dir, exist_ok=True)
    
    # Render環境の検出と情報出力
    if os.environ.get('RENDER'):
        print(f"INFO: Running on Render.com")
        print(f"INFO: Database URL = {database_url}")
        if database_url.startswith('sqlite'):
            print("WARNING: Using SQLite on Render - data may be lost on redeploy!")
    
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
