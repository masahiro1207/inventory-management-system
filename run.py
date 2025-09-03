import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    # 本番環境では環境変数からポートを取得
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    
    if debug:
        print("在庫管理システムを起動しています...")
        print("ブラウザで http://localhost:5000 にアクセスしてください")
    
    app.run(debug=debug, host='0.0.0.0', port=port)
