from app.service import run_investigation_pipeline


def main():
    result = run_investigation_pipeline("data/support_cases.csv")

    print(f"Processed candidate pairs: {result['processed_pairs']}")
    print(f"Pending reviews: {result['pending_reviews']}")


if __name__ == "__main__":
    main()
