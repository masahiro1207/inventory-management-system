import os
import io
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from app.models.inventory import Product
from app import db
from datetime import datetime

class PDFService:
    @staticmethod
    def export_inventory_pdf(dealer='', sort_by='product_name', sort_order='asc'):
        """在庫不足商品のみをPDF形式でエクスポート"""
        try:
            # 在庫不足商品のみを取得
            query = Product.query.filter(Product.current_stock < Product.min_quantity)
            if dealer:
                query = query.filter(Product.dealer == dealer)
            
            # ソートを適用
            if sort_by == 'shortage':
                # 不足数は計算値なので、min_quantity - current_stockでソート
                if sort_order == 'desc':
                    query = query.order_by((Product.min_quantity - Product.current_stock).desc())
                else:
                    query = query.order_by((Product.min_quantity - Product.current_stock).asc())
            elif hasattr(Product, sort_by):
                column = getattr(Product, sort_by)
                if sort_order == 'desc':
                    query = query.order_by(column.desc())
                else:
                    query = query.order_by(column.asc())
            
            products = query.all()
            
            if not products:
                return False, "在庫不足の商品はありません"
            
            # メモリ上でPDFを生成
            buffer = io.BytesIO()
            
            # PDFドキュメント作成（メモリ上）
            doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
            story = []
            
            # 日本語フォントの設定
            try:
                # 日本語フォントを登録
                pdfmetrics.registerFont(UnicodeCIDFont('HeiseiMin-W3'))
                font_name = 'HeiseiMin-W3'
            except:
                # フォールバック: デフォルトフォントを使用
                font_name = 'Helvetica'
            
            # スタイル設定
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=18,
                spaceAfter=30,
                alignment=1,  # 中央揃え
                fontName=font_name
            )
            
            # タイトル
            title_text = f"在庫不足レポート"
            if dealer:
                title_text += f" - {dealer}"
            title_text += f" ({datetime.now().strftime('%Y年%m月%d日 %H:%M')})"
            
            story.append(Paragraph(title_text, title_style))
            story.append(Spacer(1, 20))
            
            # 統計情報
            total_products = len(products)
            total_shortage = sum(p.min_quantity - p.current_stock for p in products)
            high_urgency = sum(1 for p in products if (p.min_quantity - p.current_stock) > 10)
            
            stats_data = [
                ['在庫不足商品数', '総不足数', '高緊急度商品数'],
                [str(total_products), str(total_shortage), str(high_urgency)]
            ]
            
            stats_table = Table(stats_data, colWidths=[2*inch, 2*inch, 2*inch])
            stats_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkred),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), font_name),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.lightcoral),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            
            story.append(stats_table)
            story.append(Spacer(1, 20))
            
            # 在庫不足商品テーブル
            table_data = [['メーカー', '商品名', '単価', '現在在庫', '最低必要数', '不足数', '取引先']]
            
            for product in products:
                shortage = product.min_quantity - product.current_stock
                row = [
                    product.manufacturer or '-',
                    product.product_name,
                    f'¥{product.unit_price:,.0f}' if product.unit_price else '-',
                    str(product.current_stock),
                    str(product.min_quantity) if product.min_quantity else '-',
                    str(shortage),
                    product.dealer or '-'
                ]
                table_data.append(row)
            
            # テーブル作成
            inventory_table = Table(table_data, colWidths=[1.5*inch, 2.5*inch, 1*inch, 1*inch, 1*inch, 1*inch, 1.5*inch])
            
            # テーブルスタイル設定
            table_style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkred),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), font_name),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('FONTNAME', (0, 1), (-1, -1), font_name),
                ('ALIGN', (2, 1), (2, -1), 'RIGHT'),  # 単価を右揃え
                ('ALIGN', (3, 1), (4, -1), 'CENTER'),  # 在庫数を中央揃え
            ])
            
            inventory_table.setStyle(table_style)
            story.append(inventory_table)
            
            # PDF生成
            doc.build(story)
            
            # バッファの位置を先頭に戻す
            buffer.seek(0)
            
            return True, buffer
            
        except Exception as e:
            return False, f"PDFエクスポートエラー: {str(e)}"
    
    @staticmethod
    def export_alerts_pdf(dealer=''):
        """在庫不足アラートをPDF形式でエクスポート"""
        try:
            # 在庫不足商品を取得
            query = Product.query.filter(Product.current_stock < Product.min_quantity)
            if dealer:
                query = query.filter(Product.dealer == dealer)
            
            low_stock_products = query.all()
            
            if not low_stock_products:
                return False, "在庫不足の商品はありません"
            
            # メモリ上でPDFを生成
            buffer = io.BytesIO()
            
            # PDFドキュメント作成（メモリ上）
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            story = []
            
            # 日本語フォントの設定
            try:
                # 日本語フォントを登録
                pdfmetrics.registerFont(UnicodeCIDFont('HeiseiMin-W3'))
                font_name = 'HeiseiMin-W3'
            except:
                # フォールバック: デフォルトフォントを使用
                font_name = 'Helvetica'
            
            # スタイル設定
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=16,
                spaceAfter=20,
                alignment=1,
                fontName=font_name
            )
            
            # タイトル
            title_text = f"在庫不足アラートレポート"
            if dealer:
                title_text += f" - {dealer}"
            title_text += f" ({datetime.now().strftime('%Y年%m月%d日 %H:%M')})"
            
            story.append(Paragraph(title_text, title_style))
            story.append(Spacer(1, 20))
            
            # アラート一覧テーブル
            table_data = [['商品名', 'メーカー', '現在在庫', '最低必要数', '不足数', '取引先', '緊急度']]
            
            for product in low_stock_products:
                shortage = product.min_quantity - product.current_stock
                urgency = '高' if shortage > 10 else '中' if shortage > 5 else '低'
                
                row = [
                    product.product_name,
                    product.manufacturer or '-',
                    str(product.current_stock),
                    str(product.min_quantity),
                    str(shortage),
                    product.dealer or '-',
                    urgency
                ]
                table_data.append(row)
            
            # テーブル作成
            alerts_table = Table(table_data, colWidths=[2*inch, 1.5*inch, 1*inch, 1*inch, 1*inch, 1.5*inch, 0.8*inch])
            
            # テーブルスタイル設定
            table_style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkred),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), font_name),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('FONTNAME', (0, 1), (-1, -1), font_name),
            ])
            
            # 緊急度による行の色分け
            for i, product in enumerate(low_stock_products, start=1):
                shortage = product.min_quantity - product.current_stock
                if shortage > 10:
                    table_style.add('BACKGROUND', (0, i), (-1, i), colors.lightcoral)
                elif shortage > 5:
                    table_style.add('BACKGROUND', (0, i), (-1, i), colors.lightyellow)
            
            alerts_table.setStyle(table_style)
            story.append(alerts_table)
            
            # PDF生成
            doc.build(story)
            
            # バッファの位置を先頭に戻す
            buffer.seek(0)
            
            return True, buffer
            
        except Exception as e:
            return False, f"アラートPDFエクスポートエラー: {str(e)}"
