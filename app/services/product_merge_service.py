"""重複商品の統合（在庫合算・フィールド選択・エイリアス引き継ぎ）。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from app import db
from app.models.inventory import OrderHistory, Product
from app.services.product_alias_service import ensure_alias


def _is_system_dummy(product: Product) -> bool:
    if product.manufacturer != "システム":
        return False
    name = product.product_name or ""
    return name.startswith("取引会社管理用_") or name.startswith("カテゴリ管理用_")


def merge_products(
    product_ids: List[int],
    *,
    manufacturer_from: int,
    product_name_from: int,
    unit_price_from: int,
    dealer_from: int,
    keep_product_id: Optional[int] = None,
) -> Product:
    """
    2〜3 件の商品を 1 件に統合する。
    採用するメーカー・商品名・単価・取引会社は呼び出し側で商品 ID を指定する。
    在庫数は合算。統合元の商品名とエイリアスは残存商品へ引き継ぐ。
    """
    unique_ids = list(dict.fromkeys(product_ids))
    if len(unique_ids) < 2 or len(unique_ids) > 3:
        raise ValueError("統合する商品は 2 件または 3 件を選択してください")

    field_sources = {
        "manufacturer": manufacturer_from,
        "product_name": product_name_from,
        "unit_price": unit_price_from,
        "dealer": dealer_from,
    }
    for key, src_id in field_sources.items():
        if src_id not in unique_ids:
            raise ValueError(f"{key} の採用元商品が選択リストに含まれていません")

    keep_id = keep_product_id if keep_product_id in unique_ids else min(unique_ids)

    products = Product.query.filter(Product.id.in_(unique_ids)).all()
    if len(products) != len(unique_ids):
        raise ValueError("指定された商品の一部が見つかりません")

    for p in products:
        if _is_system_dummy(p):
            raise ValueError("システム管理用の商品は統合できません")

    by_id: Dict[int, Product] = {p.id: p for p in products}
    keep = by_id[keep_id]
    others = [p for p in products if p.id != keep_id]

    names_to_alias: List[tuple[str, str]] = []
    for p in products:
        names_to_alias.append((p.product_name, "merge"))
        for alias in p.aliases.all():
            names_to_alias.append((alias.alias_name, "merge"))

    keep.manufacturer = by_id[manufacturer_from].manufacturer
    keep.product_name = by_id[product_name_from].product_name[:200]
    keep.unit_price = float(by_id[unit_price_from].unit_price)
    keep.dealer = by_id[dealer_from].dealer

    keep.current_stock = sum(p.current_stock for p in products)
    keep.min_quantity = max(p.min_quantity for p in products)

    if not keep.category:
        for p in products:
            if p.category:
                keep.category = p.category
                break

    for name, source in names_to_alias:
        ensure_alias(keep, name, source)

    for other in others:
        OrderHistory.query.filter_by(product_id=other.id).update(
            {OrderHistory.product_id: keep.id},
            synchronize_session=False,
        )
        db.session.delete(other)

    keep.updated_at = datetime.utcnow()
    db.session.commit()
    return keep
