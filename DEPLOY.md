# 在庫管理システム デプロイガイド

## Heroku デプロイ

### 1. Heroku CLI のインストール
```bash
# macOS
brew install heroku/brew/heroku

# Windows
# https://devcenter.heroku.com/articles/heroku-cli からダウンロード
```

### 2. Heroku にログイン
```bash
heroku login
```

### 3. アプリケーションの作成
```bash
heroku create your-app-name
```

### 4. 環境変数の設定
```bash
heroku config:set FLASK_ENV=production
heroku config:set SECRET_KEY=your-secret-key-here
```

### 5. データベースの追加（PostgreSQL）
```bash
heroku addons:create heroku-postgresql:mini
```

### 6. デプロイ
```bash
git add .
git commit -m "Initial deployment"
git push heroku main
```

### 7. アプリケーションの起動
```bash
heroku ps:scale web=1
```

### 8. ログの確認
```bash
heroku logs --tail
```

## その他のデプロイオプション

### Railway
1. Railway にログイン
2. 新しいプロジェクトを作成
3. GitHub リポジトリを接続
4. 環境変数を設定
5. デプロイ

### Render
1. Render にログイン
2. 新しい Web Service を作成
3. GitHub リポジトリを接続
4. 環境変数を設定
5. デプロイ

## 環境変数

| 変数名 | 説明 | デフォルト値 |
|--------|------|-------------|
| FLASK_ENV | Flask環境 | production |
| SECRET_KEY | Flask秘密鍵 | your-secret-key-here |
| DATABASE_URL | データベースURL | sqlite:///inventory.db |
| PORT | ポート番号 | 5000 |

## トラブルシューティング

### よくある問題

1. **ビルドエラー**
   - requirements.txt の依存関係を確認
   - Python バージョンを確認

2. **データベースエラー**
   - DATABASE_URL の設定を確認
   - データベースの初期化を確認

3. **静的ファイルエラー**
   - 静的ファイルのパスを確認
   - ファイルの存在を確認

### ログの確認
```bash
# Heroku
heroku logs --tail

# Railway
railway logs

# Render
render logs
```
