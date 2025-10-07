# 在庫管理システム デプロイガイド

## 🎯 推奨：Render.com（無料プラン）

Render.com は無料で使えるプラットフォームで、クレジットカード登録不要です。

### メリット

- ✅ 完全無料（750 時間/月 = 実質常時稼働可能）
- ✅ クレジットカード登録不要
- ✅ 自動デプロイ（GitHub と連携）
- ✅ HTTPS 自動対応
- ✅ 簡単な設定

### デメリット

- ⚠️ 非アクティブ時にスリープ（初回アクセス時に起動に数秒かかる）
- ⚠️ 無料プランでは PostgreSQL が使えない（SQLite を使用）
- ⚠️ SQLite のデータは再デプロイ時にリセットされる可能性あり

---

## Render.com デプロイ手順（最も簡単！）

### 方法 1：render.yaml を使った自動デプロイ（推奨）

1. **GitHub にコードをプッシュ**

   ```bash
   git add .
   git commit -m "Add Render configuration"
   git push origin main
   ```

2. **Render.com にアクセス**

   - https://render.com にアクセス
   - GitHub アカウントでサインアップ/ログイン

3. **新しい Web サービスを作成**

   - ダッシュボードで「New +」→「Blueprint」を選択
   - GitHub リポジトリを接続
   - このリポジトリを選択
   - `render.yaml` が自動的に検出されます

4. **デプロイ開始**

   - 「Apply」ボタンをクリック
   - 自動的にビルド＆デプロイが開始されます
   - 5-10 分程度でデプロイ完了

5. **アプリケーションにアクセス**
   - 提供された URL（例：https://inventory-management-system.onrender.com）にアクセス

### 方法 2：手動設定

1. **Render.com にサインアップ**

   - https://render.com で GitHub アカウントを使ってサインアップ

2. **新しい Web サービスを作成**

   - ダッシュボードで「New +」→「Web Service」を選択
   - GitHub リポジトリを接続
   - このリポジトリを選択

3. **設定を入力**

   - **Name**: `inventory-management-system`（任意の名前）
   - **Region**: `Oregon (US West)` または好きなリージョン
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn run:app`
   - **Instance Type**: `Free`

4. **環境変数を設定**

   「Environment」セクションで以下を追加：

   | Key              | Value                                           |
   | ---------------- | ----------------------------------------------- |
   | `PYTHON_VERSION` | `3.11.0`                                        |
   | `FLASK_ENV`      | `production`                                    |
   | `SECRET_KEY`     | ランダムな文字列（例：`your-secret-key-12345`） |
   | `DATABASE_URL`   | `sqlite:///inventory.db`                        |

5. **デプロイ**

   - 「Create Web Service」ボタンをクリック
   - ビルドとデプロイが自動的に開始されます

6. **アプリケーションにアクセス**
   - デプロイ完了後、提供された URL にアクセス

### トラブルシューティング（Render.com）

**問題 1: ビルドに失敗する**

```bash
# runtime.txtのPythonバージョンを確認
cat runtime.txt
# Python 3.11.0 になっていることを確認
```

**問題 2: アプリケーションが起動しない**

- Render のログを確認：ダッシュボードの「Logs」タブ
- `gunicorn run:app` コマンドが正しいか確認

**問題 3: データが消える**

- SQLite はエフェメラルストレージを使用
- 重要なデータは定期的にエクスポート/バックアップを推奨
- 永続化が必要な場合は有料の PostgreSQL プランを検討

**問題 4: スリープから復帰が遅い**

- 無料プランの制限です
- UptimeRobot などの外部サービスで定期的にアクセスすることで緩和可能
  - https://uptimerobot.com （無料）
  - 5 分ごとにアプリに ping を送る設定

### 自動デプロイの設定

GitHub と連携すれば、コードをプッシュするだけで自動的に再デプロイされます：

1. Render のダッシュボードで「Settings」→「Build & Deploy」
2. 「Auto-Deploy」が `Yes` になっていることを確認
3. これで GitHub に `git push` するたびに自動デプロイ！

---

## Heroku デプロイ（有料化されました）

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

| 変数名       | 説明             | デフォルト値           |
| ------------ | ---------------- | ---------------------- |
| FLASK_ENV    | Flask 環境       | production             |
| SECRET_KEY   | Flask 秘密鍵     | your-secret-key-here   |
| DATABASE_URL | データベース URL | sqlite:///inventory.db |
| PORT         | ポート番号       | 5000                   |

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
