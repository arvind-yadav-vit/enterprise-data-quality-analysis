"""
dq_pipeline.py
Reusable Data Quality audit + cleaning pipeline for the
Enterprise Data Quality & Business Impact Analysis project.

Usage:
    python3 dq_pipeline.py

Outputs:
    customers_clean.csv       - cleaned customer data
    orders_clean.csv          - cleaned order data
    dq_scorecard.csv          - the 6-dimension DQ scores (feeds Power BI)
    business_impact.csv       - cost estimates (feeds Power BI)
"""

import pandas as pd
import numpy as np
import re
from rapidfuzz import fuzz


# ---------------------------------------------------------------
# STEP 1: LOAD
# ---------------------------------------------------------------
def load_data(customers_path="customers_raw.csv", orders_path="orders_raw.csv"):
    customers = pd.read_csv(customers_path)
    orders = pd.read_csv(orders_path)
    return customers, orders


# ---------------------------------------------------------------
# STEP 2: DQ CHECKS (each function returns a score AND the detail
# needed for cleaning later - keeps audit and fix logic together
# per dimension, which is easier to maintain than splitting them)
# ---------------------------------------------------------------
def check_completeness(customers):
    total_cells = customers.shape[0] * customers.shape[1]
    total_missing = customers.isnull().sum().sum()
    score = round((1 - total_missing / total_cells) * 100, 2)
    return score


def check_uniqueness(customers):
    customers["name_normalized"] = customers["name"].str.strip().str.lower()
    duplicate_mask = customers.duplicated(subset=["name_normalized"], keep=False)
    exact_duplicates = duplicate_mask.sum()
    score = round((1 - exact_duplicates / len(customers)) * 100, 2)
    return score, duplicate_mask


def check_validity(orders):
    def detect_date_format(date_str):
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return 'YYYY-MM-DD'
        elif re.match(r'^\d{2}/\d{2}/\d{4}$', date_str):
            return 'DD/MM/YYYY'
        elif re.match(r'^\d{2}-\d{2}-\d{4}$', date_str):
            return 'MM-DD-YYYY'
        return 'UNKNOWN'

    format_map = {'YYYY-MM-DD': '%Y-%m-%d', 'MM-DD-YYYY': '%m-%d-%Y', 'DD/MM/YYYY': '%d/%m/%Y'}

    orders["date_format_detected"] = orders["order_date"].apply(detect_date_format)

    def parse_row(row):
        fmt = format_map.get(row["date_format_detected"])
        if fmt is None:
            return pd.NaT
        try:
            return pd.to_datetime(row["order_date"], format=fmt)
        except ValueError:
            return pd.NaT

    orders["order_date_parsed"] = orders.apply(parse_row, axis=1)

    invalid_dates = orders["order_date_parsed"].isna().sum()
    invalid_qty_mask = orders["quantity"] <= 0
    invalid_qty = invalid_qty_mask.sum()

    total = len(orders)
    score = round((1 - (invalid_dates + invalid_qty) / total) * 100, 2)
    return score, invalid_qty_mask


def check_consistency(customers):
    country_mapping = {
        "USA": "United States", "US": "United States", "United States": "United States",
        "UK": "United Kingdom", "United Kingdom": "United Kingdom",
        "Canada": "Canada", "Germany": "Germany", "Australia": "Australia"
    }
    customers["country_standardized"] = customers["country"].map(country_mapping)
    already_consistent = (customers["country"] == customers["country_standardized"]).sum()
    score = round((already_consistent / len(customers)) * 100, 2)
    return score


def check_accuracy(customers):
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

    def is_plausible_email(email):
        if pd.isna(email):
            return None
        return bool(re.match(email_pattern, email))

    def is_plausible_phone(phone):
        if pd.isna(phone):
            return None
        main_number = re.split(r'[xX]', phone)[0]
        digit_count = sum(c.isdigit() for c in main_number)
        return 7 <= digit_count <= 15

    customers["email_plausible"] = customers["email"].apply(is_plausible_email)
    customers["phone_plausible"] = customers["phone"].apply(is_plausible_phone)

    valid = customers["email_plausible"].sum() + customers["phone_plausible"].sum()
    checked = customers["email_plausible"].notna().sum() + customers["phone_plausible"].notna().sum()
    score = round((valid / checked) * 100, 2)
    return score


def check_timeliness(customers):
    customers["signup_date"] = pd.to_datetime(customers["signup_date"])
    today = pd.Timestamp.now().normalize()
    future = (customers["signup_date"] > today).sum()
    stale = (customers["signup_date"] < today - pd.Timedelta(days=3 * 365)).sum()
    score = round((1 - (future + stale) / len(customers)) * 100, 2)
    return score


# ---------------------------------------------------------------
# STEP 3: CLEANING (applies fixes, using the detail returned above)
# ---------------------------------------------------------------
def clean_customers(customers, duplicate_mask):
    clean = customers.copy()
    # Keep first occurrence of each normalized-name duplicate group
    clean = clean.sort_values("customer_id").drop_duplicates(subset=["name_normalized"], keep="first")
    clean["country"] = clean["country_standardized"]
    clean = clean.drop(columns=["name_normalized", "country_standardized",
                                 "email_plausible", "phone_plausible"], errors="ignore")
    return clean


def clean_orders(orders, invalid_qty_mask):
    clean = orders.copy()
    clean = clean[~invalid_qty_mask]  # drop impossible negative/zero quantity rows
    clean["order_date"] = clean["order_date_parsed"]
    clean = clean.drop(columns=["date_format_detected", "order_date_parsed"], errors="ignore")
    return clean


# ---------------------------------------------------------------
# STEP 4: BUSINESS IMPACT (same logic from Phase 4, parameterized)
# ---------------------------------------------------------------
def calculate_business_impact(duplicate_count, missing_contact_count,
                                us_fragmented, us_true):
    wasted_marketing = duplicate_count * 2.50 * 12
    at_risk_revenue = missing_contact_count * 150 * 0.30
    understatement_pct = round((1 - us_fragmented / us_true) * 100, 1)

    return pd.DataFrame([
        {"issue": "Duplicate customers", "metric": "Wasted annual marketing spend ($)", "value": wasted_marketing},
        {"issue": "Missing contact info", "metric": "At-risk revenue ($)", "value": at_risk_revenue},
        {"issue": "Country inconsistency", "metric": "US segment understatement (%)", "value": understatement_pct},
    ])


# ---------------------------------------------------------------
# MAIN PIPELINE
# ---------------------------------------------------------------
def main():
    print("Loading raw data...")
    customers, orders = load_data()

    print("Running DQ checks...")
    completeness_score = check_completeness(customers)
    uniqueness_score, duplicate_mask = check_uniqueness(customers)
    validity_score, invalid_qty_mask = check_validity(orders)
    consistency_score = check_consistency(customers)
    accuracy_score = check_accuracy(customers)
    timeliness_score = check_timeliness(customers)

    scorecard = pd.DataFrame([
        {"dimension": "Completeness", "score": completeness_score},
        {"dimension": "Uniqueness", "score": uniqueness_score},
        {"dimension": "Validity", "score": validity_score},
        {"dimension": "Consistency", "score": consistency_score},
        {"dimension": "Accuracy", "score": accuracy_score},
        {"dimension": "Timeliness", "score": timeliness_score},
    ])
    overall_score = round(scorecard["score"].mean(), 2)
    scorecard.loc[len(scorecard)] = ["Overall", overall_score]
    scorecard.to_csv("dq_scorecard.csv", index=False)
    print(scorecard)
    print(f"\nOverall Data Quality Score: {overall_score}%")

    print("\nCleaning data...")
    customers_clean = clean_customers(customers, duplicate_mask)
    orders_clean = clean_orders(orders, invalid_qty_mask)
    customers_clean.to_csv("customers_clean.csv", index=False)
    orders_clean.to_csv("orders_clean.csv", index=False)
    print(f"Customers: {len(customers)} raw -> {len(customers_clean)} clean")
    print(f"Orders: {len(orders)} raw -> {len(orders_clean)} clean")

    print("\nCalculating business impact...")
    missing_contact = customers[["email", "phone"]].isnull().any(axis=1).sum()
    us_true = (customers["country_standardized"] == "United States").sum()
    us_fragmented = (customers["country"] == "United States").sum()

    impact = calculate_business_impact(
        duplicate_count=duplicate_mask.sum(),
        missing_contact_count=missing_contact,
        us_fragmented=us_fragmented,
        us_true=us_true
    )
    impact.to_csv("business_impact.csv", index=False)
    print(impact)

    print("\nPipeline complete. Outputs written:")
    print(" - dq_scorecard.csv")
    print(" - customers_clean.csv")
    print(" - orders_clean.csv")
    print(" - business_impact.csv")


if __name__ == "__main__":
    main()