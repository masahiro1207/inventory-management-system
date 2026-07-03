"""納品書PDFから明細を読み取り在庫へ反映（ビューティガレージ形式など）。"""
from __future__ import annotations

import re
import time
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Tuple

from app import db
from app.models.inventory import Product
from app.services.product_matching import (
    DEFAULT_AMBIGUITY_MARGIN,
    DEFAULT_SIMILARITY_THRESHOLD,
    find_best_product_match,
)
from app.services.product_alias_service import (
    load_alias_map,
    register_import_name,
    sync_alias_map_entry,
)

# DB の product_name / product_code の上限に合わせる
_MAX_PRODUCT_NAME_LEN = 200
_MAX_PRODUCT_CODE_LEN = 50

# 行頭: 注文番号 S… + 商品コード + 商品名（PDF によってはコードが注文番号に連結）
# 注文行番号は -10, -100 など最大3桁。\\d+ だと -100225954 まで吸い込んでしまう。
_LINE_START_SPACED = re.compile(r"^(S\d+-\d{1,3})\s+(\S+)\s+(.+)$")
# S012004173-170ZC-1649N など英数字コードが連結
_LINE_START_GLUED_ALPHA = re.compile(
    r"^(S\d+-\d{1,3})([A-Z]{1,3}-\d+[A-Z0-9]*)\s+(.+)$"
)
# S012004173-100225954 など 6 桁商品コードが連結
_LINE_START_GLUED_NUM = re.compile(r"^(S\d+-)(\d*?)(\d{6})\s+(.+)$")
# 「2 個」「2個」「２ 個」（NFKC 後）などに対応
_QTY_LINE = re.compile(r"^([0-9]{1,9})\s*個\s*$")
# 商品名末尾に数量が付く行（例: トリシスコア KH 200ml 1 個）
_INLINE_QTY = re.compile(r"^(.+?)\s+(\d{1,9})\s*個\s*$")


def _parse_order_line_start(line: str) -> Tuple[str, str, str] | None:
    """明細行の先頭から (注文番号, 商品コード, 商品名の開始) を取り出す。"""
    m = _LINE_START_SPACED.match(line)
    if m:
        return m.group(1), m.group(2), m.group(3)

    m = _LINE_START_GLUED_ALPHA.match(line)
    if m:
        return m.group(1), m.group(2), m.group(3)

    m = _LINE_START_GLUED_NUM.match(line)
    if m:
        order_id = f"{m.group(1)}{m.group(2)}"
        return order_id, m.group(3), m.group(4)

    return None


def _split_inline_qty(text: str) -> Tuple[str, int | None]:
    """商品名文字列末尾の「N 個」を分離する。"""
    m = _INLINE_QTY.match(text.strip())
    if m:
        return m.group(1).strip(), int(m.group(2))
    return text.strip(), None


def parse_beauty_garage_delivery_text(text: str) -> List[Dict[str, Any]]:
    """
    ビューティガレージ納品書（テキスト抽出結果）から明細をパースする。
    商品名は改行で分割されるため、次の「N 個」行までを結合する。
    """
    raw = unicodedata.normalize("NFKC", (text or "").replace("\ufeff", ""))
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    items: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines):
        parsed = _parse_order_line_start(lines[i])
        if not parsed:
            i += 1
            continue
        order_id, sku, name_start = parsed
        name_start, qty = _split_inline_qty(name_start)
        name_parts = [name_start] if name_start else []
        i += 1
        while i < len(lines) and qty is None:
            line = lines[i]
            qm = _QTY_LINE.match(line)
            if qm:
                qty = int(qm.group(1))
                i += 1
                break
            if _parse_order_line_start(line):
                break
            name_parts.append(line)
            i += 1
        if qty is None:
            full_name = " ".join(name_parts)
            full_name, qty = _split_inline_qty(full_name)
            name_parts = [full_name] if full_name else []
        if qty is not None:
            full_name = " ".join(name_parts)
            full_name = re.sub(r"\s+", " ", full_name).strip()[:_MAX_PRODUCT_NAME_LEN]
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

    reader = PdfReader(file_path, strict=False)
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
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        ambiguity_margin: float = DEFAULT_AMBIGUITY_MARGIN,
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
            alias_map = load_alias_map(working_list)
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
                    alias_map=alias_map,
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
                    register_import_name(match, name, "pdf")
                    sync_alias_map_entry(alias_map, match)
                    updated_count += 1
                else:
                    timestamp = int(time.time() * 1000) % 100000
                    prefix = (preferred_dealer[:3] if preferred_dealer else "PDF").upper()
                    slip = re.sub(r"[\s/\\]+", "", str(row["slip_product_code"]))
                    # product_code は 50 文字上限。slip を短くしてから組み立てる。
                    for slip_len in (24, 16, 10, 6):
                        product_code = f"{prefix}_{slip[:slip_len]}_{timestamp:05d}"
                        if len(product_code) <= _MAX_PRODUCT_CODE_LEN:
                            break
                    product_code = product_code[:_MAX_PRODUCT_CODE_LEN]
                    while Product.query.filter_by(product_code=product_code).first():
                        timestamp += 1
                        product_code = f"{prefix}_{slip[:6]}_{timestamp:05d}"[
                            :_MAX_PRODUCT_CODE_LEN
                        ]
                    safe_name = name[:_MAX_PRODUCT_NAME_LEN]
                    new_product = Product(
                        product_code=product_code,
                        manufacturer="未設定",
                        product_name=safe_name,
                        unit_price=0.0,
                        current_stock=qty,
                        dealer=preferred_dealer if preferred_dealer else None,
                        min_quantity=5,
                        category=None,
                    )
                    db.session.add(new_product)
                    db.session.flush()
                    register_import_name(new_product, safe_name, "pdf")
                    sync_alias_map_entry(alias_map, new_product)
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
