from rapidfuzz import fuzz


def score_candidate(candidate, case_lookup):
    """
    Compute deterministic score for a candidate pair.

    Returns:
    {
        "combined_score": float,
        "bucket": "HIGH" | "LOW" | "DISCARD"
    }
    """

    case1 = case_lookup[candidate["case1_id"]]
    case2 = case_lookup[candidate["case2_id"]]

    score = 0.0

    # ------------------------
    # Same Email
    # ------------------------
    if (
        str(case1["contact_email"]).strip().lower()
        == str(case2["contact_email"]).strip().lower()
    ):
        score += 0.45

    # ------------------------
    # Similar Account
    # ------------------------
    account_score = fuzz.token_sort_ratio(
        str(case1["account_name"]),
        str(case2["account_name"]),
    )
    score += (account_score / 100) * 0.30

    # ------------------------
    # Similar Subject
    # ------------------------
    subject_score = fuzz.token_set_ratio(
        str(case1["subject"]),
        str(case2["subject"]),
    )
    score += (subject_score / 100) * 0.15

    # ------------------------
    # Subject Token Overlap
    # ------------------------
    overlap = len(
        case1["subject_tokens"].intersection(
            case2["subject_tokens"]
        )
    )

    score += (min(overlap, 5) / 5) * 0.10

    # ------------------------
    # Bucket
    # ------------------------
    if score >= 0.35:
        bucket = "HIGH"
    elif score >= 0.20:
        bucket = "LOW"
    else:
        bucket = "DISCARD"

    return {
        "combined_score": round(score, 3),
        "bucket": bucket,
    }