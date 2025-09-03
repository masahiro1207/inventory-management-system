from flask import Blueprint, request, jsonify, render_template
from app.models.inventory import Product, OrderHistory
from app.services.csv_service import CSVService
from app.services.ml_service import MLService
from app.services.pdf_service import PDFService
from app import db
from datetime import datetime
import os

inventory_bp = Blueprint('inventory', __name__)
csv_service = CSVService()
ml_service = MLService()
pdf_service = PDFService()

@inventory_bp.route('/')
def index():
    """メインページ - 在庫一覧表示"""
    products = Product.query.all()
    return render_template('index.html', products=products)

@inventory_bp.route('/alerts')
def alerts_page():
    """在庫不足アラート一覧ページ"""
    return render_template('alerts.html')

@inventory_bp.route('/settings')
def settings_page():
    """設定ページ - カテゴリ・取引会社・メーカー管理"""
    return render_template('settings.html')

@inventory_bp.route('/api/products', methods=['GET'])
def get_products():
    """商品一覧をJSONで取得（検索・ソート・フィルタ対応）"""
    try:
        # クエリパラメータの取得
        search = request.args.get('search', '')
        sort_by = request.args.get('sort_by', 'product_name')
        sort_order = request.args.get('sort_order', 'asc')
        dealer = request.args.get('dealer', '')
        
        # ベースクエリ（システム管理用ダミー商品を除外）
        query = Product.query.filter(
            db.not_(db.and_(
                Product.product_name.like('取引会社管理用_%'),
                Product.manufacturer == 'システム'
            )),
            db.not_(db.and_(
                Product.product_name.like('カテゴリ管理用_%'),
                Product.manufacturer == 'システム'
            ))
        )
        
        # 検索フィルタ
        if search:
            query = query.filter(
                db.or_(
                    Product.product_name.contains(search),
                    Product.manufacturer.contains(search),
                    Product.category.contains(search)
                )
            )
        
        # 取引会社フィルタ
        if dealer:
            query = query.filter(Product.dealer == dealer)
        
        # ソート
        if sort_order == 'desc':
            query = query.order_by(db.desc(getattr(Product, sort_by)))
        else:
            query = query.order_by(db.asc(getattr(Product, sort_by)))
        
        products = query.all()
        
        return jsonify([{
            'id': p.id,
            'manufacturer': p.manufacturer,
            'product_name': p.product_name,
            'unit_price': p.unit_price,
            'current_stock': p.current_stock,
            'min_quantity': p.min_quantity,
            'category': p.category,
            'dealer': p.dealer
        } for p in products])
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@inventory_bp.route('/api/products', methods=['POST'])
def create_product():
    """商品を手動で登録"""
    try:
        data = request.get_json()
        
        # 必須項目のチェック
        required_fields = ['product_name', 'manufacturer', 'unit_price']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'{field}は必須です'}), 400
        
        # 商品コードの生成（重複チェック付き）
        product_code = data.get('product_code')
        if not product_code:
            # 自動生成
            import time
            timestamp = int(time.time() * 1000) % 100000
            manufacturer_prefix = data['manufacturer'][:3].upper()
            product_code = f"{manufacturer_prefix}_{timestamp:05d}"
            
            # 重複チェック
            while Product.query.filter_by(product_code=product_code).first():
                timestamp += 1
                product_code = f"{manufacturer_prefix}_{timestamp:05d}"
        
        # 商品コードの重複チェック
        if Product.query.filter_by(product_code=product_code).first():
            return jsonify({'success': False, 'error': 'この商品コードは既に使用されています'}), 400
        
        # 同じ商品（商品名・メーカー・取引会社の組み合わせ）の重複チェック
        existing_product = Product.query.filter_by(
            product_name=data['product_name'],
            manufacturer=data['manufacturer'],
            dealer=data.get('dealer') if data.get('dealer') else None
        ).first()
        
        if existing_product:
            return jsonify({
                'success': False, 
                'error': f'同じ商品が既に登録されています（取引会社: {existing_product.dealer or "未設定"}）'
            }), 400
        
        # 取引会社が指定されている場合、その取引会社に既に同じ商品名・メーカーの商品があるかチェック
        if data.get('dealer'):
            same_dealer_product = Product.query.filter_by(
                product_name=data['product_name'],
                manufacturer=data['manufacturer'],
                dealer=data['dealer']
            ).first()
            
            if same_dealer_product:
                return jsonify({
                    'success': False, 
                    'error': f'取引会社「{data["dealer"]}」に同じ商品が既に登録されています'
                }), 400
        
        # 新しい商品を作成
        new_product = Product(
            product_code=product_code,
            product_name=data['product_name'],
            manufacturer=data['manufacturer'],
            unit_price=float(data['unit_price']),
            current_stock=int(data.get('current_stock', 0)),
            min_quantity=int(data.get('min_quantity', 0)),
            category=data.get('category') if data.get('category') else None,
            dealer=data.get('dealer') if data.get('dealer') else None
        )
        
        db.session.add(new_product)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': '商品を登録しました',
            'product_id': new_product.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@inventory_bp.route('/api/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    """商品情報の更新"""
    try:
        product = Product.query.get_or_404(product_id)
        data = request.get_json()
        
        if 'current_stock' in data:
            product.current_stock = int(data['current_stock'])
        if 'min_quantity' in data:
            product.min_quantity = int(data['min_quantity'])
        if 'unit_price' in data:
            product.unit_price = float(data['unit_price'])
        if 'category' in data:
            product.category = data['category']
        if 'dealer' in data:
            product.dealer = data['dealer']
        
        product.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({'success': True, 'message': '商品情報を更新しました'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@inventory_bp.route('/api/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    """商品の削除"""
    try:
        product = Product.query.get_or_404(product_id)
        
        # 関連する注文履歴も削除
        OrderHistory.query.filter_by(product_id=product_id).delete()
        
        # 商品を削除
        db.session.delete(product)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '商品を削除しました'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@inventory_bp.route('/api/products/<int:product_id>/stock', methods=['POST'])
def adjust_stock(product_id):
    """在庫数の手動調整"""
    try:
        product = Product.query.get_or_404(product_id)
        data = request.get_json()
        adjustment = int(data['adjustment'])
        
        product.current_stock += adjustment
        product.updated_at = datetime.utcnow()
        
        # 注文履歴に記録
        if adjustment > 0:
            order = OrderHistory(
                product_id=product_id,
                quantity=adjustment,
                dealer=data.get('dealer', '手動調整')
            )
            db.session.add(order)
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'在庫を{adjustment:+d}調整しました',
            'new_stock': product.current_stock
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@inventory_bp.route('/api/dealers', methods=['GET'])
def get_dealers():
    """取引会社一覧を取得"""
    try:
        # 商品に設定されている取引会社を取得（システム管理用ダミー商品も含む）
        product_dealers = db.session.query(Product.dealer).distinct().filter(Product.dealer.isnot(None)).all()
        dealer_list = [dealer[0] for dealer in product_dealers if dealer[0]]
        
        # 重複を除去してソート
        dealer_list = sorted(list(set(dealer_list)))
        
        return jsonify({'success': True, 'dealers': dealer_list})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@inventory_bp.route('/api/categories', methods=['GET'])
def get_categories():
    """カテゴリ一覧を取得"""
    try:
        categories = db.session.query(Product.category).distinct().filter(Product.category.isnot(None)).all()
        category_list = [category[0] for category in categories if category[0]]
        return jsonify({'success': True, 'categories': category_list})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@inventory_bp.route('/api/manufacturers', methods=['GET'])
def get_manufacturers():
    """メーカー一覧を取得"""
    try:
        manufacturers = db.session.query(Product.manufacturer).distinct().filter(Product.manufacturer.isnot(None)).all()
        manufacturer_list = [manufacturer[0] for manufacturer in manufacturers if manufacturer[0]]
        return jsonify({'success': True, 'manufacturers': manufacturer_list})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@inventory_bp.route('/api/settings/bulk-update', methods=['POST'])
def bulk_update_settings():
    """カテゴリ・取引会社・メーカーの一括更新"""
    try:
        data = request.get_json()
        action = data.get('action')  # 'add' or 'remove'
        field = data.get('field')    # 'category', 'dealer', 'manufacturer'
        values = data.get('values', [])
        
        if not all([action, field, values]):
            return jsonify({'success': False, 'error': '必要なパラメータが不足しています'})
        
        if action == 'add':
            # 既存の商品に新しい値を設定
            updated_count = 0
            for value in values:
                if value.strip():
                    # 空のカテゴリを持つ商品を更新
                    if field == 'category':
                        result = Product.query.filter_by(category=None).update({Product.category: value.strip()})
                        updated_count += result
                    elif field == 'dealer':
                        # 取引会社の場合は、未設定の商品に設定
                        result = Product.query.filter_by(dealer=None).update({Product.dealer: value.strip()})
                        updated_count += result
                    elif field == 'manufacturer':
                        result = Product.query.filter_by(manufacturer=None).update({Product.manufacturer: value.strip()})
                        updated_count += result
            
            # カテゴリの場合は、商品が存在しなくても登録成功とする
            if field == 'category':
                # カテゴリが存在しない場合は、ダミー商品を作成してカテゴリを登録
                if updated_count == 0:
                    for value in values:
                        if value.strip():
                            # 既にそのカテゴリのダミー商品が存在するかチェック
                            existing_dummy = Product.query.filter_by(
                                product_name=f"カテゴリ管理用_{value.strip()}",
                                manufacturer="システム",
                                category=value.strip()
                            ).first()
                            
                            if not existing_dummy:
                                # ダミー商品を作成
                                import time
                                timestamp = int(time.time() * 1000) % 100000
                                product_code = f"CATEGORY_{timestamp:05d}"
                                
                                # 商品コードの重複チェック
                                while Product.query.filter_by(product_code=product_code).first():
                                    timestamp += 1
                                    product_code = f"CATEGORY_{timestamp:05d}"
                                
                                dummy_product = Product(
                                    product_code=product_code,
                                    product_name=f"カテゴリ管理用_{value.strip()}",
                                    manufacturer="システム",
                                    category=value.strip(),
                                    unit_price=0,
                                    current_stock=0,
                                    min_quantity=0,
                                    dealer="システム管理"
                                )
                                db.session.add(dummy_product)
                                updated_count += 1
                
                db.session.commit()
                return jsonify({'success': True, 'message': f'{len(values)}件のカテゴリを登録しました（更新件数: {updated_count}件）'})
            
            # 取引会社の場合は、商品が存在しなくても登録成功とする
            if field == 'dealer':
                # 取引会社が存在しない場合は、ダミー商品を作成して取引会社を登録
                if updated_count == 0:
                    for value in values:
                        if value.strip():
                            # 既にその取引会社のダミー商品が存在するかチェック
                            existing_dummy = Product.query.filter_by(
                                product_name=f"取引会社管理用_{value.strip()}",
                                manufacturer="システム",
                                dealer=value.strip()
                            ).first()
                            
                            if not existing_dummy:
                                # ダミー商品を作成
                                import time
                                timestamp = int(time.time() * 1000) % 100000
                                product_code = f"DEALER_{timestamp:05d}"
                                
                                # 商品コードの重複チェック
                                while Product.query.filter_by(product_code=product_code).first():
                                    timestamp += 1
                                    product_code = f"DEALER_{timestamp:05d}"
                                
                                dummy_product = Product(
                                    product_code=product_code,
                                    product_name=f"取引会社管理用_{value.strip()}",
                                    manufacturer="システム",
                                    dealer=value.strip(),
                                    unit_price=0,
                                    current_stock=0,
                                    min_quantity=0,
                                    category="システム管理"
                                )
                                db.session.add(dummy_product)
                                updated_count += 1
                
                db.session.commit()
                return jsonify({'success': True, 'message': f'{len(values)}件の取引会社を登録しました（更新件数: {updated_count}件）'})
            
            # 商品が存在しない場合は、メッセージのみ返す（テスト商品は作成しない）
            if updated_count == 0:
                return jsonify({'success': True, 'message': f'{len(values)}件の{field}を登録しました（対象商品なし）'})
            
            db.session.commit()
            return jsonify({'success': True, 'message': f'{len(values)}件の{field}を追加しました（更新件数: {updated_count}件）'})
        
        elif action == 'remove':
            # 指定された値を削除（Noneに設定）
            removed_count = 0
            for value in values:
                if field == 'category':
                    result = Product.query.filter_by(category=value).update({Product.category: None})
                    removed_count += result
                elif field == 'dealer':
                    result = Product.query.filter_by(dealer=value).update({Product.dealer: None})
                    removed_count += result
                elif field == 'manufacturer':
                    result = Product.query.filter_by(manufacturer=value).update({Product.manufacturer: None})
                    removed_count += result
            
            db.session.commit()
            return jsonify({'success': True, 'message': f'{len(values)}件の{field}を削除しました（影響商品数: {removed_count}件）'})
        
        return jsonify({'success': False, 'error': '無効なアクションです'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@inventory_bp.route('/api/settings/delete-test-products', methods=['POST'])
def delete_test_products():
    """テスト商品の削除"""
    try:
        # テスト商品を検索（商品名に「テスト商品_」が含まれる商品）
        test_products = Product.query.filter(Product.product_name.like('テスト商品_%')).all()
        
        if not test_products:
            return jsonify({'success': True, 'message': '削除対象のテスト商品はありません'})
        
        # テスト商品を削除
        deleted_count = 0
        for product in test_products:
            db.session.delete(product)
            deleted_count += 1
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'{deleted_count}件のテスト商品を削除しました'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@inventory_bp.route('/api/debug/duplicate-products', methods=['GET'])
def debug_duplicate_products():
    """重複商品のデバッグ情報を取得"""
    try:
        # 商品名・メーカー・取引会社の組み合わせで重複をチェック
        from sqlalchemy import func
        
        # 重複商品の検索
        duplicates = db.session.query(
            Product.product_name,
            Product.manufacturer,
            Product.dealer,
            func.count(Product.id).label('count'),
            func.group_concat(Product.id).label('product_ids')
        ).group_by(
            Product.product_name,
            Product.manufacturer,
            Product.dealer
        ).having(func.count(Product.id) > 1).all()
        
        result = []
        for dup in duplicates:
            result.append({
                'product_name': dup.product_name,
                'manufacturer': dup.manufacturer,
                'dealer': dup.dealer or '未設定',
                'count': dup.count,
                'product_ids': dup.product_ids.split(',')
            })
        
        return jsonify({
            'success': True,
            'duplicates': result,
            'total_duplicates': len(result)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@inventory_bp.route('/api/debug/clean-duplicates', methods=['POST'])
def clean_duplicate_products():
    """重複商品のクリーンアップ（古い方を削除）"""
    try:
        from sqlalchemy import func
        
        # 重複商品の検索
        duplicates = db.session.query(
            Product.product_name,
            Product.manufacturer,
            Product.dealer,
            func.min(Product.id).label('keep_id'),
            func.count(Product.id).label('count')
        ).group_by(
            Product.product_name,
            Product.manufacturer,
            Product.dealer
        ).having(func.count(Product.id) > 1).all()
        
        deleted_count = 0
        for dup in duplicates:
            # 古い商品（IDが大きい方）を削除
            old_products = Product.query.filter(
                Product.product_name == dup.product_name,
                Product.manufacturer == dup.manufacturer,
                Product.dealer == dup.dealer,
                Product.id != dup.keep_id
            ).all()
            
            for product in old_products:
                db.session.delete(product)
                deleted_count += 1
        
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'{deleted_count}件の重複商品を削除しました'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@inventory_bp.route('/api/csv/upload', methods=['POST'])
def upload_csv():
    """CSVファイルのアップロードと処理"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'ファイルが選択されていません'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'ファイルが選択されていません'}), 400
        
        if not file.filename.endswith('.csv'):
            return jsonify({'success': False, 'error': 'CSVファイルのみ対応しています'}), 400
        
        # 取引会社の指定を取得
        dealer = request.form.get('dealer', '')
        
        # ファイルを保存
        filename = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = os.path.join('uploads', filename)
        os.makedirs('uploads', exist_ok=True)
        file.save(filepath)
        
        # CSV処理（取引会社を指定）
        success, message = csv_service.process_inventory_csv(filepath, dealer)
        
        # 一時ファイルを削除
        os.remove(filepath)
        
        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'error': message}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@inventory_bp.route('/api/csv/export', methods=['GET'])
def export_csv():
    """在庫データのCSVエクスポート"""
    try:
        dealer = request.args.get('dealer', '')
        success, result = csv_service.export_inventory_csv(dealer)
        if success:
            return jsonify({'success': True, 'file_path': result})
        else:
            return jsonify({'success': False, 'error': result}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@inventory_bp.route('/api/pdf/export', methods=['GET'])
def export_pdf():
    """在庫データのPDFエクスポート"""
    try:
        dealer = request.args.get('dealer', '')
        success, result = pdf_service.export_inventory_pdf(dealer)
        if success:
            return jsonify({'success': True, 'file_path': result})
        else:
            return jsonify({'success': False, 'error': result}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@inventory_bp.route('/api/products/bulk-update', methods=['POST'])
def bulk_update_products():
    """商品の一括更新（カテゴリ、取引会社、メーカー）"""
    try:
        data = request.get_json()
        field = data.get('field')  # 'category', 'dealer', 'manufacturer'
        current_value = data.get('current_value')
        new_value = data.get('new_value')
        
        if not all([field, current_value, new_value]):
            return jsonify({'success': False, 'error': '必要なパラメータが不足しています'})
        
        # 指定された値を持つ商品を更新
        if field == 'category':
            result = Product.query.filter_by(category=current_value).update({Product.category: new_value})
        elif field == 'dealer':
            result = Product.query.filter_by(dealer=current_value).update({Product.dealer: new_value})
        elif field == 'manufacturer':
            result = Product.query.filter_by(manufacturer=current_value).update({Product.manufacturer: new_value})
        else:
            return jsonify({'success': False, 'error': '無効なフィールドです'})
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'{result}件の商品の{field}を更新しました'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@inventory_bp.route('/api/products/csv-upload', methods=['POST'])
def upload_csv_products():
    """商品名のみのCSVアップロード（重複チェック付き）"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'ファイルが選択されていません'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'ファイルが選択されていません'}), 400
        
        if not file.filename.endswith('.csv'):
            return jsonify({'success': False, 'error': 'CSVファイルのみ対応しています'}), 400
        
        # デフォルト値を取得
        default_category = request.form.get('default_category', '')
        default_dealer = request.form.get('default_dealer', '')
        default_manufacturer = request.form.get('default_manufacturer', '')
        
        # CSVファイルを読み込み
        import pandas as pd
        import io
        
        # ファイル内容を読み込み
        content = file.read().decode('utf-8')
        df = pd.read_csv(io.StringIO(content), header=None)
        
        # 商品名のリストを取得
        product_names = df[0].dropna().str.strip().tolist()
        
        if not product_names:
            return jsonify({'success': False, 'error': '有効な商品名が含まれていません'}), 400
        
        # 既存の商品名をチェック
        existing_products = Product.query.filter(Product.product_name.in_(product_names)).all()
        existing_names = [p.product_name for p in existing_products]
        
        # 新規登録対象の商品名
        new_product_names = [name for name in product_names if name not in existing_names]
        
        if not new_product_names:
            return jsonify({'success': False, 'error': '全ての商品名が既に登録されています'}), 400
        
        # 新規商品を登録
        added_count = 0
        for product_name in new_product_names:
            # ユニークな商品コードを生成
            timestamp = datetime.now().strftime('%H%M%S')
            product_code = f"CSV_{timestamp}_{added_count:03d}"
            
            new_product = Product(
                product_code=product_code,
                product_name=product_name,
                manufacturer=default_manufacturer if default_manufacturer else '未設定',
                category=default_category if default_category else '未設定',
                dealer=default_dealer if default_dealer else '未設定',
                unit_price=100,  # デフォルト価格を100円に設定
                current_stock=0,  # 初期在庫は0
                min_quantity=5    # 初期最小必要数は5に設定
            )
            db.session.add(new_product)
            added_count += 1
        
        db.session.commit()
        
        message = f'{added_count}件の商品を登録しました'
        if existing_names:
            message += f'（{len(existing_names)}件は既存のためスキップ）'
        
        return jsonify({'success': True, 'message': message})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@inventory_bp.route('/api/products/bulk-category-update', methods=['POST'])
def bulk_update_category():
    """選択された商品の一括カテゴリ設定"""
    try:
        data = request.get_json()
        category = data.get('category')
        product_ids = data.get('product_ids', [])
        
        if not category:
            return jsonify({'success': False, 'error': 'カテゴリ名が指定されていません'})
        
        if not product_ids:
            return jsonify({'success': False, 'error': '商品が選択されていません'})
        
        # 選択された商品のカテゴリを更新
        result = Product.query.filter(Product.id.in_(product_ids)).update({Product.category: category})
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'{result}件の商品のカテゴリを設定しました'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@inventory_bp.route('/api/products/bulk-dealer-update', methods=['POST'])
def bulk_update_dealer():
    """選択された商品の一括取引会社設定"""
    try:
        data = request.get_json()
        dealer = data.get('dealer')
        product_ids = data.get('product_ids', [])
        
        if not dealer:
            return jsonify({'success': False, 'error': '取引会社名が指定されていません'})
        
        if not product_ids:
            return jsonify({'success': False, 'error': '商品が選択されていません'})
        
        # 選択された商品の取引会社を更新
        result = Product.query.filter(Product.id.in_(product_ids)).update({Product.dealer: dealer})
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'{result}件の商品の取引会社を設定しました'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@inventory_bp.route('/api/products/bulk-delete', methods=['POST'])
def bulk_delete_products():
    """選択された商品の一括削除"""
    try:
        data = request.get_json()
        product_ids = data.get('product_ids', [])
        
        if not product_ids:
            return jsonify({'success': False, 'error': '削除する商品が選択されていません'})
        
        # 選択された商品を削除
        result = Product.query.filter(Product.id.in_(product_ids)).delete(synchronize_session=False)
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'{result}件の商品を削除しました'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@inventory_bp.route('/api/ml/train', methods=['POST'])
def train_ml_model():
    """機械学習モデルの訓練"""
    try:
        success, message = ml_service.train_model()
        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'error': message}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@inventory_bp.route('/api/ml/recommendations', methods=['GET'])
def get_recommendations():
    """注文推奨の取得"""
    try:
        dealer = request.args.get('dealer', '')
        success, recommendations = ml_service.get_order_recommendations(dealer)
        if success:
            return jsonify({
                'success': True, 
                'recommendations': [{
                    'product_id': r['product'].id,
                    'product_name': r['product'].product_name,
                    'manufacturer': r['product'].manufacturer,
                    'reason': r['reason'],
                    'priority': r['priority'],
                    'suggested_quantity': r['suggested_quantity'],
                    'current_stock': r['product'].current_stock,
                    'min_quantity': r['product'].min_quantity
                } for r in recommendations]
            })
        else:
            return jsonify({'success': False, 'error': recommendations}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@inventory_bp.route('/api/alerts', methods=['GET'])
def get_alerts():
    """在庫アラートの取得"""
    try:
        dealer = request.args.get('dealer', '')
        
        # 在庫が最低必要数を下回っている商品
        query = Product.query.filter(Product.current_stock < Product.min_quantity)
        if dealer:
            query = query.filter(Product.dealer == dealer)
        
        low_stock_products = query.all()
        
        alerts = []
        for product in low_stock_products:
            alerts.append({
                'type': 'low_stock',
                'product_name': product.product_name,
                'manufacturer': product.manufacturer,
                'current_stock': product.current_stock,
                'min_quantity': product.min_quantity,
                'shortage': product.min_quantity - product.current_stock,
                'dealer': product.dealer
            })
        
        return jsonify({'success': True, 'alerts': alerts})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
