import pandas as pd
import os
from app.models.inventory import Product
from app import db
from datetime import datetime

class CSVService:
    @staticmethod
    def process_inventory_csv(file_path, dealer=''):
        """在庫CSVファイルを処理してデータベースに保存（取引会社別対応）"""
        try:
            # CSVファイルを読み込み（エンコーディング自動検出とフォールバック）
            import chardet
            with open(file_path, 'rb') as f:
                raw_data = f.read()
                detected_encoding = chardet.detect(raw_data)['encoding']
            
            # エンコーディングの優先順位（CP932とSHIFT_JISを優先）
            encodings_to_try = [
                detected_encoding,
                'cp932',
                'shift_jis',
                'utf-8',
                'euc-jp'
            ]
            
            df = None
            for encoding in encodings_to_try:
                if encoding:
                    try:
                        df = pd.read_csv(file_path, encoding=encoding)
                        print(f"CSV読み込み成功: {encoding}")
                        break
                    except (UnicodeDecodeError, UnicodeError):
                        continue
            
            if df is None:
                return False, "CSVファイルのエンコーディングが判別できませんでした"
            
            # 取引会社別の列マッピング定義
            dealer_mappings = {
                'トヨタ': {
                    'manufacturer': ['メーカー名', 'manufacturer', 'メーカー'],
                    'product_name': ['商品名', 'product_name', '商品'],
                    'unit_price': ['単価', 'unit_price', '価格', 'サロン価格'],
                    'quantity': ['数量', 'quantity', '個数']
                },
                'ホンダ': {
                    'manufacturer': ['メーカー名', 'manufacturer', 'メーカー', 'ブランド'],
                    'product_name': ['商品名', 'product_name', '商品', '品名'],
                    'unit_price': ['単価', 'unit_price', '価格', '販売価格'],
                    'quantity': ['数量', 'quantity', '個数', '入荷数']
                },
                '日産': {
                    'manufacturer': ['メーカー名', 'manufacturer', 'メーカー', 'メーカーコード'],
                    'product_name': ['商品名', 'product_name', '商品', '品名', 'JANコード'],
                    'unit_price': ['単価', 'unit_price', '価格', '希望小売価格'],
                    'quantity': ['数量', 'quantity', '個数', '入荷数']
                },
                'マツダ': {
                    'manufacturer': ['メーカー名', 'manufacturer', 'メーカー', 'ブランド'],
                    'product_name': ['商品名', 'product_name', '商品', '品名'],
                    'unit_price': ['単価', 'unit_price', '価格', 'サロン価格'],
                    'quantity': ['数量', 'quantity', '個数', '入荷数']
                },
                'GAMO': {
                    'manufacturer': ['メーカー名', 'manufacturer', 'メーカー', 'ブランド'],
                    'product_name': ['商品名', 'product_name', '商品', '品名'],
                    'unit_price': ['サロン価（税抜）', 'サロン価格', '単価', 'unit_price', '価格'],
                    'quantity': ['数量', 'quantity', '個数', '入荷数']
                }
            }
            
            # 汎用マッピング（上記に該当しない場合）
            default_mapping = {
                'manufacturer': ['メーカー名', 'manufacturer', 'メーカー', 'ブランド', 'メーカーコード'],
                'product_name': ['商品名', 'product_name', '商品', '品名', 'JANコード'],
                'unit_price': ['サロン価（税抜）', 'サロン価格', '単価', 'unit_price', '価格', 'メーカー希望小売価格', '販売価格'],
                'quantity': ['数量', 'quantity', '個数', '入荷数']
            }
            
            # 取引会社に応じたマッピングを選択
            mapping = dealer_mappings.get(dealer, default_mapping)
            
            # 実際の列名を特定
            actual_columns = {}
            for target, possible_names in mapping.items():
                found = False
                for col_name in possible_names:
                    if col_name in df.columns:
                        actual_columns[target] = col_name
                        found = True
                        break
                if not found:
                    return False, f"必要な列 '{target}' が見つかりません。利用可能な列: {list(df.columns)}"
            
            processed_count = 0
            for _, row in df.iterrows():
                # 既存商品の確認（メーカー名と商品名で照合）
                existing_product = Product.query.filter_by(
                    manufacturer=str(row[actual_columns['manufacturer']]),
                    product_name=str(row[actual_columns['product_name']]),
                    dealer=dealer if dealer else None
                ).first()
                
                if existing_product:
                    # 既存商品の更新
                    existing_product.unit_price = float(row[actual_columns['unit_price']])
                    if pd.notna(row[actual_columns['quantity']]):
                        existing_product.current_stock += int(row[actual_columns['quantity']])
                    existing_product.updated_at = datetime.utcnow()
                else:
                    # 新規商品の作成（商品コードは自動生成、重複回避）
                    import time
                    timestamp = int(time.time() * 1000) % 100000  # 5桁のタイムスタンプ
                    manufacturer_prefix = str(row[actual_columns['manufacturer']])[:3].upper()
                    product_code = f"{manufacturer_prefix}_{timestamp:05d}"
                    
                    # 商品コードの重複チェック
                    while Product.query.filter_by(product_code=product_code).first():
                        timestamp += 1
                        product_code = f"{manufacturer_prefix}_{timestamp:05d}"
                    
                    new_product = Product(
                        product_code=product_code,
                        manufacturer=str(row[actual_columns['manufacturer']]),
                        product_name=str(row[actual_columns['product_name']]),
                        unit_price=float(row[actual_columns['unit_price']]),
                        current_stock=int(row[actual_columns['quantity']]) if pd.notna(row[actual_columns['quantity']]) else 0,
                        dealer=dealer if dealer else None
                    )
                    db.session.add(new_product)
                
                processed_count += 1
            
            db.session.commit()
            return True, f"{processed_count}件の商品を処理しました（取引会社: {dealer or '未指定'}）"
            
        except Exception as e:
            db.session.rollback()
            return False, f"エラーが発生しました: {str(e)}"
    
    @staticmethod
    def export_inventory_csv(dealer=''):
        """在庫データをCSV形式でエクスポート（取引会社別）"""
        try:
            query = Product.query
            if dealer:
                query = query.filter(Product.dealer == dealer)
            
            products = query.all()
            
            data = []
            for product in products:
                data.append({
                    'manufacturer': product.manufacturer,
                    'product_name': product.product_name,
                    'unit_price': product.unit_price,
                    'current_stock': product.current_stock,
                    'min_quantity': product.min_quantity,
                    'category': product.category,
                    'dealer': product.dealer
                })
            
            df = pd.DataFrame(data)
            dealer_suffix = f"_{dealer}" if dealer else ""
            export_path = os.path.join('reports', f'inventory_export{dealer_suffix}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
            df.to_csv(export_path, index=False, encoding='utf-8-sig')
            
            return True, export_path
            
        except Exception as e:
            return False, f"エクスポートエラー: {str(e)}"
