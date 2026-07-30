from datetime import datetime
from rapidfuzz import fuzz


def compare_fields(case1, case2):
    """
    Compare important CRM fields.
    """

    return {
        "same_account": (
            str(case1["account_name"]).strip().lower()
            == str(case2["account_name"]).strip().lower()
        ),
        "same_email": (
            str(case1["contact_email"]).strip().lower()
            == str(case2["contact_email"]).strip().lower()
        ),
        "same_priority": (
            str(case1["priority"]).strip().lower()
            == str(case2["priority"]).strip().lower()
        ),
        "same_channel": (
            str(case1["channel"]).strip().lower()
            == str(case2["channel"]).strip().lower()
        ),
        "same_status": (
            str(case1["status"]).strip().lower()
            == str(case2["status"]).strip().lower()
        ),
    }


def fuzzy_score(case1, case2):
    """
    Calculate fuzzy similarity scores.
    """

    return {
        "account_score": fuzz.token_sort_ratio(
            str(case1["account_name"]),
            str(case2["account_name"])
        ),
        "subject_score": fuzz.token_set_ratio(
            str(case1["subject"]),
            str(case2["subject"])
        ),
        "description_score": fuzz.token_set_ratio(
            str(case1["description"]),
            str(case2["description"])
        ),
    }


def timeline_gap(case1, case2):
    """
    Calculate time difference between case creation.
    """

    t1 = datetime.fromisoformat(str(case1["created_at"]))
    t2 = datetime.fromisoformat(str(case2["created_at"]))

    minutes = abs((t2 - t1).total_seconds()) / 60

    return {
        "gap_minutes": round(minutes, 2)
    }


def find_other_cases(case, df):
    """
    Find other cases for the same account or email.
    """

    account = str(case["account_name"]).strip().lower()
    email = str(case["contact_email"]).strip().lower()

    account_cases = df[
        df["account_name"].str.lower() == account
    ]["case_id"].tolist()

    email_cases = df[
        df["contact_email"].str.lower() == email
    ]["case_id"].tolist()

    return {
        "same_account_cases": account_cases,
        "same_email_cases": email_cases,
        "account_case_count": len(account_cases),
        "email_case_count": len(email_cases),
    }