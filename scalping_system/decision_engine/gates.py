from .schema import MarketEvidence


def quality_gate(e: MarketEvidence):
    if e.data_quality < 0.70:
        return False, "DATA_QUALITY_LOW"

    if e.evidence_quality < 0.70:
        return False, "EVIDENCE_QUALITY_LOW"

    if not 0 <= e.data_quality <= 1:
        return False, "DATA_QUALITY_INVALID"

    if not 0 <= e.evidence_quality <= 1:
        return False, "EVIDENCE_QUALITY_INVALID"

    return True, "QUALITY_ACCEPTED"
