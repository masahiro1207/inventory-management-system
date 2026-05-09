"""納品書PDFから明細を読み取り在庫へ反映（ビューティガレージ形式など）。"""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple

from app import db
from app.models.inventory import Product
from app.services.product_matching import find_best_product_match

# 行頭: 注文番号 S… + 商品コード（数字のみ or 英数字） + 商品名の開始
_LINE_START = re.compile(r"^(S\d+-\d+)\s+(\S+)\s+(.+)$")
_QTY_LINE = re.compile(r"^(\d+)\s+個\s*$")


def parse_beauty_garage_delivery_text(text: str) -> List[Dict[str, Any]]:
    """
    ビューティガレージ納品書（テキスト抽出結果）から明細をパースする。
    商品名は改行で分割されるため、次の「N 個」行までを結合する。
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    items: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines):
        m = _LINE_START.match(lines[i])
        if not m:
            i += 1
            continue
        order_id, sku, name_start = m.group(1), m.group(2), m.group(3)
        name_parts = [name_start]
        i += 1
        qty: int | None = None
        while i < len(lines):
            qm = _QTY_LINE.match(lines[i])
            if qm:
                qty = int(qm.group(1))
                i += 1
                break
            name_parts.append(lines[i])
            i += 1
        if qty is not None:
            full_name = " ".join(name_parts)
            full_name = re.sub(r"\s+", " ", full_name).strip()
            items.append(
                {
                    "order_id": order_id,
                    "slip_product_code": sku,
                    "product_name": full_name,
                    "quantity": qty,
                }
            )
    return items


def extract_pdf_text(file_path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    parts: List[str] = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            parts.append(t)
    return "\n".join(parts)


class DeliveryPdfImportService:
    @staticmethod
    def process_delivery_pdf(
        file_path: str,
        preferred_dealer: str = "",
        *,
        similarity_threshold: float = 0.80,
        ambiguity_margin: float = 0.04,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        納品書PDFを処理。対応: ビューティガレージ系（ご注文番号 S…・商品コード・商品名・数量 個）。
        商品照合は CSV 取込と同じ（全取引会社候補 + preferred_dealer 優先）。
        """
        try:
            raw = extract_pdf_text(file_path)
            line_items = parse_beauty_garage_delivery_text(raw)
            if not line_items:
                return (
                    False,
                    "PDFから明細行を読み取れませんでした。"
                    "納品書（ご注文番号・商品コード・数量 個）形式か確認してください。",
                    {},
                )

            working_list: List[Any] = list(Product.query.all())
            updated_count = 0
            added_count = 0
            ambiguous: List[Dict[str, Any]] = []

            for row in line_items:
                name = row["product_name"]
                qty = row["quantity"]
                match, score, reason = find_best_product_match(
                    name,
                    working_list,
                    preferred_dealer=preferred_dealer,
                    similarity_threshold=similarity_threshold,
                    ambiguity_margin=ambiguity_margin,
                )
                if reason == "ambiguous":
                    ambiguous.append(
                        {
                            "product_name": name,
                            "quantity": qty,
                            "best_score": round(score, 3),
                        }
                    )
                    continue
                if match is not None:
                    match.current_stock += qty
                    match.updated_at = datetime.utcnow()
                    updated_count += 1
                else:
                    timestamp = int(time.time() * 1000) % 100000
                    prefix = (preferred_dealer[:3] if preferred_dealer else "PDF").upper()
                    slip = row["slip_product_code"]
                    product_code = f"{prefix}_{slip}_{timestamp:05d}"
                    while Product.query.filter_by(product_code=product_code).first():
                        timestamp += 1
                        product_code = f"{prefix}_{slip}_{timestamp:05d}"
                    new_product = Product(
                        product_code=product_code,
                        manufacturer="未設定",
                        product_name=name,
                        unit_price=0.0,
                        current_stock=qty,
                        dealer=preferred_dealer if preferred_dealer else None,
                        min_quantity=5,
                        category=None,
                    )
                    db.session.add(new_product)
                    working_list.append(new_product)
                    added_count += 1

            db.session.commit()
            detail = {
                "lines": len(line_items),
                "updated": updated_count,
                "added": added_count,
                "ambiguous": ambiguous,
                "similarity_threshold": similarity_threshold,
            }
            msg = (
                f"PDF {len(line_items)} 行を処理しました"
                f"（在庫加算 {updated_count} 件、新規 {added_count} 件）"
            )
            if ambiguous:
                msg += (
                    f" 類似が曖昧でスキップ: {len(ambiguous)} 件"
                    "（表記を統一するか手動登録してください）。"
                )
            return True, msg, detail
        except Exception as e:
            db.session.rollback()
            return False, f"PDF取込エラー: {str(e)}", {}
