from decision_engine import MarketEvidence, make_decision


evidence = MarketEvidence(
    symbol="BTCUSDT",
    fisher=0.82,
    rsi=61.4,
    smc_bias="BULLISH",
    trend="BULLISH",
    volume_quality="HIGH",
    data_quality=0.96,
    evidence_quality=0.91,
)

result = make_decision(evidence)

print("=" * 60)
print("DECISION ENGINE V1")
print("=" * 60)
print("Symbol     :", result.symbol)
print("Decision   :", result.decision)
print("Score      :", result.score)
print("Confidence :", result.confidence)
print("Allowed    :", result.allowed)
print("Reasons    :")

for reason in result.reason_codes:
    print("  -", reason)
