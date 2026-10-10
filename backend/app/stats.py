"""Tiny dependency-free statistics helpers."""
import math


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def agreement_metrics(pred, ref):
    """Compare two equally long lists (pred vs reference). Returns None if empty."""
    pairs = [(p, r) for p, r in zip(pred, ref) if p is not None and r is not None]
    n = len(pairs)
    if n == 0:
        return None
    errs = [p - r for p, r in pairs]
    mae = sum(abs(e) for e in errs) / n
    rmse = math.sqrt(sum(e * e for e in errs) / n)
    bias = sum(errs) / n
    mp, mr = sum(p for p, _ in pairs) / n, sum(r for _, r in pairs) / n
    sp = math.sqrt(sum((p - mp) ** 2 for p, _ in pairs))
    sr = math.sqrt(sum((r - mr) ** 2 for _, r in pairs))
    corr = (sum((p - mp) * (r - mr) for p, r in pairs) / (sp * sr)) if sp > 0 and sr > 0 else None
    return {"n": n, "mae": round(mae, 2), "rmse": round(rmse, 2), "bias": round(bias, 2),
            "correlation": None if corr is None else round(corr, 3)}
