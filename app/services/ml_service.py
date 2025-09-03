import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from datetime import datetime, timedelta
import joblib
import os
from app.models.inventory import Product, OrderHistory
from app import db

class MLService:
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.model_path = 'models/demand_forecast_model.pkl'
        self.scaler_path = 'models/demand_scaler.pkl'
        
    def prepare_training_data(self, dealer=''):
        """注文履歴から学習データを準備（取引会社別対応）"""
        try:
            # 注文履歴データを取得
            query = db.session.query(OrderHistory)
            if dealer:
                query = query.join(Product).filter(Product.dealer == dealer)
            
            orders = query.all()
            
            if len(orders) < 10:  # データが少なすぎる場合
                return False, "学習に十分なデータがありません（最低10件必要）"
            
            # データフレームに変換
            data = []
            for order in orders:
                data.append({
                    'product_id': order.product_id,
                    'quantity': order.quantity,
                    'order_date': order.order_date,
                    'month': order.order_date.month,
                    'day_of_week': order.order_date.weekday(),
                    'quarter': (order.order_date.month - 1) // 3 + 1
                })
            
            df = pd.DataFrame(data)
            
            # 商品ごとの統計情報を追加
            product_stats = df.groupby('product_id').agg({
                'quantity': ['mean', 'std', 'count'],
                'order_date': ['min', 'max']
            }).reset_index()
            
            product_stats.columns = ['product_id', 'avg_quantity', 'std_quantity', 'order_count', 'first_order', 'last_order']
            
            # 最終注文からの日数を計算
            latest_date = df['order_date'].max()
            product_stats['days_since_last_order'] = (latest_date - product_stats['last_order']).dt.days
            
            return True, product_stats
            
        except Exception as e:
            return False, f"データ準備エラー: {str(e)}"
    
    def train_model(self, dealer=''):
        """需要予測モデルを訓練（取引会社別対応）"""
        try:
            success, data = self.prepare_training_data(dealer)
            if not success:
                return False, data
            
            # 特徴量の準備
            X = data[['avg_quantity', 'std_quantity', 'order_count', 'days_since_last_order']].fillna(0)
            y = data['avg_quantity']  # 予測対象：平均注文量
            
            # データの分割
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            
            # スケーリング
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)
            
            # モデルの訓練
            self.model = RandomForestRegressor(n_estimators=100, random_state=42)
            self.model.fit(X_train_scaled, y_train)
            
            # モデルの保存（取引会社別）
            dealer_suffix = f"_{dealer}" if dealer else ""
            model_path = f'models/demand_forecast_model{dealer_suffix}.pkl'
            scaler_path = f'models/demand_scaler{dealer_suffix}.pkl'
            
            os.makedirs('models', exist_ok=True)
            joblib.dump(self.model, model_path)
            joblib.dump(self.scaler, scaler_path)
            
            # 精度評価
            train_score = self.model.score(X_train_scaled, y_train)
            test_score = self.model.score(X_test_scaled, y_test)
            
            dealer_info = f"（取引会社: {dealer}）" if dealer else ""
            return True, f"モデル訓練完了{dealer_info} - 訓練精度: {train_score:.3f}, テスト精度: {test_score:.3f}"
            
        except Exception as e:
            return False, f"モデル訓練エラー: {str(e)}"
    
    def predict_demand(self, product_id, dealer=''):
        """特定商品の需要を予測（取引会社別対応）"""
        try:
            if self.model is None:
                # 保存されたモデルを読み込み
                dealer_suffix = f"_{dealer}" if dealer else ""
                model_path = f'models/demand_forecast_model{dealer_suffix}.pkl'
                scaler_path = f'models/demand_scaler{dealer_suffix}.pkl'
                
                if os.path.exists(model_path):
                    self.model = joblib.load(model_path)
                    self.scaler = joblib.load(scaler_path)
                else:
                    return False, "モデルが訓練されていません"
            
            # 商品の統計情報を取得
            orders = db.session.query(OrderHistory).filter_by(product_id=product_id).all()
            
            if len(orders) < 3:
                return False, "予測に十分なデータがありません"
            
            # 特徴量の計算
            quantities = [order.quantity for order in orders]
            latest_order = max(orders, key=lambda x: x.order_date)
            days_since_last = (datetime.utcnow() - latest_order.order_date).days
            
            features = np.array([[
                np.mean(quantities),
                np.std(quantities),
                len(orders),
                days_since_last
            ]])
            
            # 予測
            features_scaled = self.scaler.transform(features)
            predicted_demand = self.model.predict(features_scaled)[0]
            
            return True, {
                'predicted_demand': max(0, int(predicted_demand)),
                'confidence': 0.8,  # 簡易的な信頼度
                'next_order_date': datetime.utcnow() + timedelta(days=30)  # 簡易的な次回注文予定日
            }
            
        except Exception as e:
            return False, f"予測エラー: {str(e)}"
    
    def get_order_recommendations(self, dealer=''):
        """注文推奨商品のリストを取得（取引会社別対応）"""
        try:
            query = Product.query
            if dealer:
                query = query.filter(Product.dealer == dealer)
            
            products = query.all()
            recommendations = []
            
            for product in products:
                # 在庫が最低必要数を下回っている商品
                if product.current_stock < product.min_quantity:
                    recommendations.append({
                        'product': product,
                        'reason': '在庫不足',
                        'priority': 'high',
                        'suggested_quantity': product.min_quantity - product.current_stock + 10
                    })
                    continue
                
                # 需要予測による推奨
                success, prediction = self.predict_demand(product.id, dealer)
                if success:
                    predicted_demand = prediction['predicted_demand']
                    if predicted_demand > product.current_stock:
                        recommendations.append({
                            'product': product,
                            'reason': '需要予測による推奨',
                            'priority': 'medium',
                            'suggested_quantity': predicted_demand - product.current_stock
                        })
            
            # 優先度順にソート
            recommendations.sort(key=lambda x: 0 if x['priority'] == 'high' else 1)
            
            return True, recommendations
            
        except Exception as e:
            return False, f"推奨取得エラー: {str(e)}"
