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
            
            # 全角・半角を統一する関数
            def normalize_text(text):
                if not text:
                    return ''
                return text.replace('　', ' ').replace('０', '0').replace('１', '1').replace('２', '2').replace('３', '3').replace('４', '4').replace('５', '5').replace('６', '6').replace('７', '7').replace('８', '8').replace('９', '9').lower()
            
            # 既存商品を事前に取得して正規化されたキーでマップ化
            existing_products = Product.query.all()
            existing_products_map = {}
            for product in existing_products:
                key = f"{normalize_text(product.manufacturer)}|{normalize_text(product.product_name)}"
                existing_products_map[key] = product
            
            processed_count = 0
            updated_count = 0
            added_count = 0
            
            for _, row in df.iterrows():
                manufacturer = str(row[actual_columns['manufacturer']]).strip()
                product_name = str(row[actual_columns['product_name']]).strip()
                unit_price = float(row[actual_columns['unit_price']])
                quantity = int(row[actual_columns['quantity']]) if pd.notna(row[actual_columns['quantity']]) else 0
                
                # 正規化されたキーで既存商品を検索
                normalized_manufacturer = normalize_text(manufacturer)
                normalized_product_name = normalize_text(product_name)
                key = f"{normalized_manufacturer}|{normalized_product_name}"
                existing_product = existing_products_map.get(key)
                
                if existing_product:
                    # 既存商品の更新（単価を更新し、在庫を追加）
                    existing_product.unit_price = unit_price
                    existing_product.current_stock += quantity
                    existing_product.updated_at = datetime.utcnow()
                    updated_count += 1
                else:
                    # 新規商品の作成（商品コードは自動生成、重複回避）
                    import time
                    timestamp = int(time.time() * 1000) % 100000  # 5桁のタイムスタンプ
                    manufacturer_prefix = manufacturer[:3].upper()
                    product_code = f"{manufacturer_prefix}_{timestamp:05d}"
                    
                    # 商品コードの重複チェック
                    while Product.query.filter_by(product_code=product_code).first():
                        timestamp += 1
                        product_code = f"{manufacturer_prefix}_{timestamp:05d}"
                    
                    new_product = Product(
                        product_code=product_code,
                        manufacturer=manufacturer,
                        product_name=product_name,
                        unit_price=unit_price,
                        current_stock=quantity,
                        dealer=dealer if dealer else None,
                        min_quantity=5,  # デフォルトの最低必要数
                        category=None    # デフォルトでカテゴリは未設定
                    )
                    db.session.add(new_product)
                    added_count += 1
                
                processed_count += 1
            
            db.session.commit()
            message = f"{processed_count}件の商品を処理しました（取引会社: {dealer or '未指定'}）"
            if added_count > 0:
                message += f" - 新規追加: {added_count}件"
            if updated_count > 0:
                message += f" - 既存商品更新: {updated_count}件"
            return True, message
            
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
