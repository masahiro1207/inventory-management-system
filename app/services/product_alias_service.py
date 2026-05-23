"""商品名エイリアス（PDF/CSV の正式名称など）。表示名は Product.product_name を優先。"""
from __future__ import annotations

from typing import Any, List, Optional

from app import db
from app.models.inventory import Product, ProductAlias
from app.services.product_matching import normalize_product_name

_MAX_ALIAS_LEN = 200


def ensure_alias(
    product: Product,
    alias_name: str,
    source: str = "",
) -> None:
    """取込名・旧名称などをエイリアスとして登録（表示名と同一なら登録しない）。"""
    if product is None or product.id is None:
        return
    name = (alias_name or "").strip()[:_MAX_ALIAS_LEN]
    if not name:
        return
    norm = normalize_product_name(name)
    if norm == normalize_product_name(product.product_name):
        return
    for existing in product.aliases.all():
        if normalize_product_name(existing.alias_name) == norm:
            return
    db.session.add(
        ProductAlias(
            product_id=product.id,
            alias_name=name,
            source=source or None,
        )
    )


def register_import_name(product: Product, import_name: str, source: str) -> None:
    """PDF/CSV 取込後、取込時の商品名をエイリアスに残す（後から表示名を変えても照合可能）。"""
    ensure_alias(product, import_name, source)


def on_product_renamed(product: Product, old_name: str, new_name: str) -> None:
    """手動で商品名変更したとき、旧名称をエイリアスに保存（PDF/CSV 照合用）。"""
    old = (old_name or "").strip()[:_MAX_ALIAS_LEN]
    new = (new_name or "").strip()
    if not old or normalize_product_name(old) == normalize_product_name(new):
        return
    norm = normalize_product_name(old)
    for existing in product.aliases.all():
        if normalize_product_name(existing.alias_name) == norm:
            return
    db.session.add(
        ProductAlias(
            product_id=product.id,
            alias_name=old,
            source="rename",
        )
    )


def sync_alias_map_entry(alias_map: dict[int, List[str]], product: Product) -> None:
    """メモリ上の alias_map を DB のエイリアスと同期（同一取込内の2行目以降用）。"""
    if product.id is None:
        return
    alias_map[product.id] = [a.alias_name for a in product.aliases.all()]


def load_alias_map(products: List[Any]) -> dict[int, List[str]]:
    """照合用: product_id -> エイリアス名リスト。"""
    ids = [p.id for p in products if getattr(p, "id", None)]
    if not ids:
        return {}
    rows = ProductAlias.query.filter(ProductAlias.product_id.in_(ids)).all()
    result: dict[int, List[str]] = {}
    for row in rows:
        result.setdefault(row.product_id, []).append(row.alias_name)
    return result
