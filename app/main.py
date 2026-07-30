import os

from dotenv import load_dotenv
from app.database import init_db, save_investigation
load_dotenv()
from app.agent import DuplicateInvestigationAgent
from app.candidate_generator import generate_candidates, load_cases
from app.candidate_ranker import score_candidate


def main():
    # Load cases
    init_db()
    df = load_cases("data/support_cases.csv")

    # API Key
    API_KEY = os.getenv("GOOGLE_API_KEY")

    if not API_KEY:
        raise ValueError(
            "GOOGLE_API_KEY environment variable is not set."
        )

    # Initialize AI Agent
    agent = DuplicateInvestigationAgent(
        api_key=API_KEY,
        dataframe=df,
    )

    # Create lookup for O(1) access
    case_lookup = {
        row["case_id"]: row
        for _, row in df.iterrows()
    }

    # Generate raw candidates
    candidates = generate_candidates(df)

    filtered_candidates = []

    # Score every candidate
    for candidate in candidates:

        result = score_candidate(candidate, case_lookup)

        candidate["combined_score"] = result["combined_score"]
        candidate["bucket"] = result["bucket"]

        if result["bucket"] == "HIGH":
            filtered_candidates.append(candidate)

    # Sort by score
    filtered_candidates.sort(
        key=lambda x: x["combined_score"],
        reverse=True,
    )

    # Save candidate generation audit
    with open(
        "logs/candidate_generation.txt",
        "w",
        encoding="utf-8",
    ) as file:

        file.write(f"Total Raw Candidates: {len(candidates)}\n")
        file.write(
            f"High Priority Candidates: {len(filtered_candidates)}\n"
        )
        file.write("=" * 80 + "\n\n")

        for candidate in candidates:

            file.write(
                f"{candidate['case1_id']} <--> {candidate['case2_id']}\n"
            )

            file.write(
                f"Reasons: {', '.join(candidate['reasons'])}\n"
            )

            file.write(
                f"Combined Score: {candidate['combined_score']:.3f}\n"
            )

            file.write(
                f"Bucket: {candidate['bucket']}\n"
            )

            file.write("-" * 80 + "\n")

    print(f"Total Raw Candidates: {len(candidates)}")
    print(
        f"High Priority Candidates: {len(filtered_candidates)}"
    )

    # -----------------------------
    # AI Investigation
    # -----------------------------

    print("\nStarting AI Investigation...\n")

    investigation_results = []

    top_candidates = filtered_candidates[:10]

    for candidate in top_candidates:

        case1 = case_lookup[candidate["case1_id"]].to_dict()
        case2 = case_lookup[candidate["case2_id"]].to_dict()

        print("=" * 80)
        print(
            f"Investigating "
            f"{candidate['case1_id']} vs {candidate['case2_id']}"
        )
        try:
            result = agent.investigate(case1, case2)

            investigation_id = save_investigation(result)

            investigation_results.append(result)

            verdict = result["verdict"]

            print(f"Investigation ID: {investigation_id}")
            print("Status: PENDING HUMAN REVIEW")

            print(
                f"Verdict: {verdict['verdict']} | "
                f"Confidence: {verdict['confidence']}"
            )
        except Exception as e:
            print(
                f"Investigation failed for "
                f"{candidate['case1_id']} vs "
                f"{candidate['case2_id']}"
            )
            print(e)

    # Save investigation log
    with open(
        "logs/agent_investigation.txt",
        "w",
        encoding="utf-8",
    ) as file:

        for result in investigation_results:

            verdict = result["verdict"]

            file.write("=" * 80 + "\n")

            file.write(
                f"{result['case1_id']} vs {result['case2_id']}\n"
            )

            file.write(
                f"Verdict: {verdict['verdict']}\n"
            )

            file.write(
                f"Confidence: {verdict['confidence']}\n"
            )

            file.write("Evidence:\n")

            for evidence in verdict["evidence"]:
                file.write(f"- {evidence}\n")

            file.write("\n")

    print(
        f"\nAI Investigation completed for "
        f"{len(investigation_results)} candidate pairs."
    )

    print(
        "\nAgent investigation log saved to "
        "logs/agent_investigation.txt"
    )


if __name__ == "__main__":
    main()