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
    database_url = os.environ.get('DATABASE_URL', 'sqlite:///inventory.db')
    
    # PostgreSQLのURLを修正
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    # 本番環境ではPostgreSQLを優先使用
    if os.environ.get('RAILWAY_ENVIRONMENT') and not database_url.startswith('postgresql://'):
        # Railway環境でPostgreSQLが利用できない場合はSQLiteを使用
        database_url = 'sqlite:////tmp/inventory.db'
    
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
        
        # Railway環境では/tmpディレクトリも作成
        if os.environ.get('RAILWAY_ENVIRONMENT'):
            os.makedirs('/tmp', exist_ok=True)
    
    return app
