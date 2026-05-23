"""商品名の正規化・照合（完全一致 + 類似度、複数取引会社を跨いだ同一商品を考慮）。"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Sequence, Tuple

# 類似度がこの値未満なら別商品扱い
DEFAULT_SIMILARITY_THRESHOLD = 0.60
# 1位と2位の類似度の差がこの値未満なら曖昧（誤マージ防止）。取引会社優先で決められる場合は採用する。
DEFAULT_AMBIGUITY_MARGIN = 0.04


def normalize_product_name(text: Any) -> str:
    """照合用に商品名を正規化（NFKC・空白・全角数字など）。"""
    if text is None:
        return ""
    try:
        import pandas as pd

        if isinstance(text, float) and pd.isna(text):
            return ""
    except ImportError:
        pass
    s = str(text).strip()
    if not s or s.lower() == "nan":
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("　", " ")
    for fw, hw in zip("０１２３４５６７８９", "0123456789"):
        s = s.replace(fw, hw)
    s = re.sub(r"\s+", " ", s)
    return s.casefold()


def name_similarity(a: str, b: str) -> float:
    na, nb = normalize_product_name(a), normalize_product_name(b)
    if not na or not nb:
        return 0.0
    return float(SequenceMatcher(None, na, nb).ratio())


def dealer_tier(product: Any, preferred_dealer: str) -> int:
    """
    アップロード時に選んだ取引会社に対する「紐付け優先度」。
    高いほど在庫を合算すべき行として優先する。
    """
    if not (preferred_dealer and preferred_dealer.strip()):
        return 0
    pref = preferred_dealer.strip()
    d = (getattr(product, "dealer", None) or "").strip()
    if d == pref:
        return 2
    if d in ("", "未設定"):
        return 1
    return 0


def _pick_among_exact(
    hits: Sequence[Any], preferred_dealer: str
) -> Tuple[Any, float, str]:
    """正規化後同一商品名が複数行あるとき、取引会社優先で1件に絞る。"""
    ranked = sorted(
        hits,
        key=lambda p: (-dealer_tier(p, preferred_dealer), getattr(p, "id", 0)),
    )
    return ranked[0], 1.0, "exact"


def _names_for_product(product: Any, alias_map: Dict[int, List[str]]) -> List[str]:
    """照合に使う名称（表示名 product_name + 登録済みエイリアス）。"""
    names: List[str] = []
    display = getattr(product, "product_name", "") or ""
    if display:
        names.append(display)
    pid = getattr(product, "id", None)
    if pid is not None:
        for alias in alias_map.get(pid, []):
            if alias:
                names.append(alias)
    return names


def _best_similarity(candidate_name: str, names: Sequence[str]) -> float:
    if not names:
        return 0.0
    return max(name_similarity(candidate_name, n) for n in names)


def find_best_product_match(
    candidate_name: str,
    products: List[Any],
    *,
    preferred_dealer: str = "",
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ambiguity_margin: float = DEFAULT_AMBIGUITY_MARGIN,
    alias_map: Optional[Dict[int, List[str]]] = None,
) -> Tuple[Optional[Any], float, str]:
    """
    既存商品から最も近い1件を返す。候補は取引会社で絞らず全件対象とし、
    同一商品を別取引会社から仕入れる場合でも名前が一致すれば在庫加算先として選べる。

    preferred_dealer にアップロード時の取引会社を渡すと、同点付近ではその行を優先する。

    Returns:
        (product | None, score, reason)
        reason: 'exact' | 'fuzzy' | 'none' | 'ambiguous'
    """
    cand = normalize_product_name(candidate_name)
    if not cand:
        return None, 0.0, "none"

    pool = list(products)
    if alias_map is None:
        from app.services.product_alias_service import load_alias_map

        alias_map = load_alias_map(pool)

    exact_hits = []
    for p in pool:
        for n in _names_for_product(p, alias_map):
            if normalize_product_name(n) == cand:
                exact_hits.append(p)
                break
    if exact_hits:
        p, s, r = _pick_among_exact(exact_hits, preferred_dealer)
        return p, s, r

    scored: List[Tuple[Any, float, int]] = []
    for p in pool:
        sim = _best_similarity(candidate_name, _names_for_product(p, alias_map))
        if sim <= 0:
            continue
        tier = dealer_tier(p, preferred_dealer)
        scored.append((p, sim, tier))

    if not scored:
        return None, 0.0, "none"

    scored.sort(
        key=lambda x: (-x[1], -x[2], getattr(x[0], "id", 0)),
    )
    best_p, best_s, best_tier = scored[0]
    if best_s < similarity_threshold:
        return None, best_s, "none"

    if len(scored) >= 2:
        _p2, second_s, second_tier = scored[1]
        gap = best_s - second_s
        if gap < ambiguity_margin:
            if best_tier > second_tier:
                return best_p, best_s, "fuzzy"
            if best_tier == second_tier:
                return None, best_s, "ambiguous"
            # best_tier < second_tier かつ類似度差が小さい → 順位付けミスなので再考: ソート済みなので起きない
            return None, best_s, "ambiguous"

    return best_p, best_s, "fuzzy"
