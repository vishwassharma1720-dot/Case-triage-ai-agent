import pandas as pd
from rapidfuzz import fuzz
import re

STOP_WORDS = {
    "the", "a", "an", "to", "of", "for", "in", "on", "with",
    "is", "are", "and", "or", "my", "your", "our",
    "issue", "problem", "unable", "please", "help"
}





def normalize_text(text):
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return text.strip()


def get_subject_tokens(subject):
    subject = normalize_text(subject)

    return {
        word
        for word in subject.split()
        if word not in STOP_WORDS and len(word) > 2
    }

def load_cases(file_path):
    df = pd.read_csv(file_path)

    df["subject_tokens"] = df["subject"].apply(get_subject_tokens)

    return df


def add_candidate(candidate_map, case1, case2, reason):

    pair = tuple(sorted([case1["case_id"], case2["case_id"]]))

    if pair not in candidate_map:
        candidate_map[pair] = {
            "case1_id": pair[0],
            "case2_id": pair[1],
            "reasons": []
        }

    if reason not in candidate_map[pair]["reasons"]:
        candidate_map[pair]["reasons"].append(reason)


def generate_candidates(df):

    candidate_map = {}

    # Normalize account names once
    df["account_name_norm"] = df["account_name"].fillna("").apply(normalize_text)

    # -----------------------------
    # Rule 1 : Same Email
    # -----------------------------

    email_groups = df.groupby("contact_email")

    for _, group in email_groups:

        if len(group) < 2:
            continue

        group = group.reset_index(drop=True)

        for i in range(len(group)):
            for j in range(i + 1, len(group)):

                add_candidate(
                    candidate_map,
                    group.iloc[i],
                    group.iloc[j],
                    "Same Email"
                )

    # -----------------------------
    # Rule 2 : Similar Account
    # (Blocking by first token)
    # -----------------------------

    df["account_block"] = df["account_name_norm"].apply(
        lambda x: x.split()[0] if x else ""
    )

    account_blocks = df.groupby("account_block")

    for _, block in account_blocks:

        if len(block) < 2:
            continue

        block = block.reset_index(drop=True)

        for i in range(len(block)):
            for j in range(i + 1, len(block)):

                case1 = block.iloc[i]
                case2 = block.iloc[j]

                score = fuzz.token_sort_ratio(
                    case1["account_name_norm"],
                    case2["account_name_norm"]
                )

                if score >= 80:
                    subject_score = fuzz.token_set_ratio(
                        str(case1["subject"]),
                        str(case2["subject"])
                    )

                    if subject_score >= 70:
                        add_candidate(
                            candidate_map,
                            case1,
                            case2,
                            "Similar Account"
                        )

    # -----------------------------
    # Rule 3 : Subject Token Overlap
    # -----------------------------
    df["subject_tokens"] = df["subject"].apply(get_subject_tokens)

    for i in range(len(df)):
        for j in range(i + 1, len(df)):

            case1 = df.iloc[i]
            case2 = df.iloc[j]

            overlap = len(
                case1["subject_tokens"].intersection(
                    case2["subject_tokens"]
                )
            )

            if overlap >= 2:

                subject_score = fuzz.token_set_ratio(
                    str(case1["subject"]),
                    str(case2["subject"])
                )

                if subject_score >= 80:

                    add_candidate(
                        candidate_map,
                        case1,
                        case2,
                        "Subject Token Overlap"
                    )

    return list(candidate_map.values())