"""
generate_data.py
Generates a deliberately messy 'customers' and 'orders' dataset
simulating a retail company's database, for the Enterprise Data
Quality & Business Impact Analysis project.
"""

import pandas as pd
import numpy as np
import random
from faker import Faker
from datetime import datetime, timedelta

fake = Faker()
Faker.seed(42)
random.seed(42)
np.random.seed(42)

N_CUSTOMERS = 500
N_ORDERS = 1500

# ---------- 1. Generate CUSTOMERS table ----------
customers = []
for i in range(1, N_CUSTOMERS + 1):
    customer_id = f"CUST{i:05d}"
    name = fake.name()
    email = fake.email()
    phone = fake.phone_number()
    country = random.choice(
        ["USA", "United States", "US", "Canada", "United Kingdom", "UK", "Germany", "Australia"]
    )  # inconsistent naming injected on purpose
    signup_date = fake.date_between(start_date="-3y", end_date="today")

    customers.append({
        "customer_id": customer_id,
        "name": name,
        "email": email,
        "phone": phone,
        "country": country,
        "signup_date": signup_date
    })

df_customers = pd.DataFrame(customers)

# Inject missing emails/phones (~15%) - simulates optional field at signup
for col in ["email", "phone"]:
    missing_idx = df_customers.sample(frac=0.15, random_state=1).index
    df_customers.loc[missing_idx, col] = np.nan

# Inject duplicate customers with slightly altered names (simulates re-signup / merge issue)
dupes = df_customers.sample(n=25, random_state=2).copy()
dupes["customer_id"] = [f"CUST{90000+i:05d}" for i in range(len(dupes))]
dupes["name"] = dupes["name"].apply(lambda n: n.upper() if random.random() > 0.5 else n + " ")
df_customers = pd.concat([df_customers, dupes], ignore_index=True)

# ---------- 2. Generate ORDERS table ----------
orders = []
valid_customer_ids = df_customers["customer_id"].tolist()

for i in range(1, N_ORDERS + 1):
    order_id = f"ORD{i:06d}"

    # Inject referential integrity break: ~3% of orders point to a customer that doesn't exist
    if random.random() < 0.03:
        customer_id = f"CUST{random.randint(90000, 99999):05d}"
    else:
        customer_id = random.choice(valid_customer_ids)

    # Inconsistent date formats - simulates system migration mid-year
    order_date = fake.date_between(start_date="-2y", end_date="today")
    if random.random() < 0.3:
        order_date_str = order_date.strftime("%d/%m/%Y")
    elif random.random() < 0.5:
        order_date_str = order_date.strftime("%m-%d-%Y")
    else:
        order_date_str = order_date.strftime("%Y-%m-%d")

    quantity = random.randint(1, 10)
    if random.random() < 0.02:
        quantity = -quantity  # impossible value: negative quantity

    unit_price = round(random.uniform(5, 500), 2)
    if random.random() < 0.01:
        unit_price = unit_price * 1000  # outlier: extra-zero style data entry error

    orders.append({
        "order_id": order_id,
        "customer_id": customer_id,
        "order_date": order_date_str,
        "quantity": quantity,
        "unit_price": unit_price
    })

df_orders = pd.DataFrame(orders)

# ---------- 3. Save to CSV ----------
df_customers.to_csv("customers_raw.csv", index=False)
df_orders.to_csv("orders_raw.csv", index=False)

print("Done.")
print(f"customers_raw.csv -> {len(df_customers)} rows")
print(f"orders_raw.csv -> {len(df_orders)} rows")