"""Dynamic Time Warping con Sakoe-Chiba constraint."""

import math


def dtw_distance(seq_a: list, seq_b: list, feature_keys: list,
               feature_ranges: dict = None, window: int = None) -> float:
    """Constrained DTW tra due sequenze di feature vector, con normalizzazione.

    seq_a, seq_b: liste di dict con le stesse chiavi
    feature_keys: chiavi da confrontare
    feature_ranges: dict {key: {min, max}} per normalizzare
    window: Sakoe-Chiba band (default = len(seq_b) // 4)
    """
    n = len(seq_a)
    m = len(seq_b)
    if n == 0 or m == 0:
        return float('inf')

    if window is None:
        window = max(max(n, m) // 2, 2)

    def norm_value(key, value):
        if feature_ranges and key in feature_ranges:
            r = feature_ranges[key]
            span = r["max"] - r["min"]
            if span > 0:
                return (value - r["min"]) / span
        return value

    def dist(a, b):
        total = 0.0
        for k in feature_keys:
            va = norm_value(k, a.get(k, 0.0))
            vb = norm_value(k, b.get(k, 0.0))
            total += (va - vb) ** 2
        return math.sqrt(total)

    # Inizializza matrice
    dp = [[float('inf')] * m for _ in range(n)]
    dp[0][0] = dist(seq_a[0], seq_b[0])

    for i in range(1, n):
        for j in range(max(0, i - window), min(m, i + window + 1)):
            cost = dist(seq_a[i], seq_b[j])
            best = dp[i - 1][j]
            if j > 0:
                best = min(best, dp[i][j - 1])
                best = min(best, dp[i - 1][j - 1])
            dp[i][j] = cost + best

    return dp[n - 1][m - 1] / max(n, m)
