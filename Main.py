from datetime import datetime
expenses = []

while True:
    print("\n===== Expense Tracker =====")
    print("1. Add Expense")
    print("2. View Analysis")
    print("3. Exit")

    choice = input("Enter your choice: ")
    if choice == "1":
        name = input("Enter Expense Name: ")
        category = input("Enter Category: ").lower().strip()
        amount = float(input("Enter Amount: "))

        date = datetime.now().strftime("%Y-%m-%d")

        expense = {
            "name": name,
            "category": category,
            "amount": amount
        }

        expenses.append(expense)

        with open("expenses.csv", "a") as file:
            file.write(f"{date},{name},{category},{amount}\n")

        print("✅ Expense added!")
    elif choice == "2":
        with open("expenses.csv", "r") as file:
            lines = file.readlines()

        data = []

        for line in lines:
            parts = line.strip().split(",")

            data.append({
                "date": parts[0],
                "name": parts[1],
                "category": parts[2],
                "amount": float(parts[3])
            })

        print("\n===== ANALYSIS REPORT =====")

        total_file = sum(item["amount"] for item in data)
        print("Total Expense:", total_file)

        category_total_file = {}

        for item in data:
            cat = item["category"]
            category_total_file[cat] = category_total_file.get(cat, 0) + item["amount"]

        print("\nCategory-wise Expense:")
        for cat, amt in category_total_file.items():
            print(f"{cat} : ₹{amt}")

        # Insights
        if category_total_file:
            highest_category = max(category_total_file, key=category_total_file.get)
            print(f"\n You spend most on {highest_category}")

        if total_file > 0:
            for cat, amt in category_total_file.items():
                percent = (amt / total_file) * 100
                if percent > 40:
                    print(f"⚠️ High spending on {cat} ({percent:.1f}%)")

        if len(data) < 3:
            print("⚠️ Not enough data")

        if "food" in category_total_file:
            food_spent = category_total_file["food"]
            if food_spent > 500:
                save = food_spent * 0.2
                print(f" Save ₹{save:.0f} by reducing food expenses")
    elif choice == "3":
        print("Exiting...")
        break


# indentation end
with open("expenses.csv", "r") as file:
    lines = file.readlines()
    print(lines)
print("\nData from file:")

data = []

for line in lines:
    parts = line.strip().split(",")

    date = parts[0]
    name = parts[1]
    category = parts[2]
    amount = float(parts[3])

    item = {
        "date": date,
        "name": name,
        "category": category,
        "amount": amount
    }

    data.append(item)

#  CHECK OUTPUT
print("\nProcessed Data:")
print(data)

# Analysis from FILE data

total_file = sum(item["amount"] for item in data)
print("\nTotal Expense (from file):", total_file)

category_total_file = {}

for item in data:
    cat = item["category"]
    category_total_file[cat] = category_total_file.get(cat, 0) + item["amount"]

print("\nCategory-wise Expense (from file):")
for cat, amt in category_total_file.items():
    print(cat, ":", amt)

# Insight Highest spending category
highest_category = max(category_total_file, key=category_total_file.get)

print("\n Insight:")
print(f"You spend most on {highest_category}")

if total_file > 0:
    for cat, amt in category_total_file.items():
        percent = (amt / total_file) * 100

        if percent > 40:
            print(f"⚠️ You are spending too much on {cat} ({percent:.1f}%)")
            
if len(data) < 3:
    print("⚠️ Not enough data to analyze properly")

#  Saving suggestion
if "food" in category_total_file:
    food_spent = category_total_file["food"]

    if food_spent > 500:
        save = food_spent * 0.2
        print(f"💡 You can save around ₹{save:.0f} by reducing food expenses")


print("\nAll Expenses:")
for exp in expenses:
    print(f"{exp['name']} | {exp['category']} | ₹{exp['amount']}")

# Total expense
total = sum(exp["amount"] for exp in expenses)
print("\nTotal Expense:", total)

# Category-wise total
category_total = {}

for exp in expenses:
    cat = exp["category"]
    category_total[cat] = category_total.get(cat, 0) + exp["amount"]

print("\nCategory-wise Expense:")
for cat, amt in category_total.items():
    print(cat, ":", amt)