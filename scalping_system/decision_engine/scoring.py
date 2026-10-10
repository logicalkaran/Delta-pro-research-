from .schema import MarketEvidence


def calculate_score(e: MarketEvidence):
    score = 0.0
    reasons = []

    # Fisher
    if e.fisher >= 0.5:
        score += 2.0
        reasons.append("FISHER_BULLISH")
    elif e.fisher <= -0.5:
        score -= 2.0
        reasons.append("FISHER_BEARISH")

    # RSI
    if 50 <= e.rsi <= 70:
        score += 1.0
        reasons.append("RSI_BULLISH_ZONE")
    elif 30 <= e.rsi < 50:
        score -= 1.0
        reasons.append("RSI_BEARISH_ZONE")

    # SMC
    if e.smc_bias.upper() == "BULLISH":
        score += 2.0
        reasons.append("SMC_BULLISH")
    elif e.smc_bias.upper() == "BEARISH":
        score -= 2.0
        reasons.append("SMC_BEARISH")

    # Trend
    if e.trend.upper() == "BULLISH":
        score += 2.0
        reasons.append("TREND_BULLISH")
    elif e.trend.upper() == "BEARISH":
        score -= 2.0
        reasons.append("TREND_BEARISH")

    # Volume
    if e.volume_quality.upper() == "HIGH":
        score += 1.0
        reasons.append("VOLUME_HIGH")

    return score, reasons
