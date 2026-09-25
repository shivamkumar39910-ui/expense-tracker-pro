import tkinter as tk
from datetime import datetime

def add_expense():
    def save_data():
        name = entry_name.get()
        category = entry_category.get().lower().strip()
        subcategory = entry_category.get().lower().strip()
        try:
            amount = float(entry_amount.get())
        except:
            result_label.config(text="❌ Invalid amount")
            return

        date = datetime.now().strftime("%Y-%m-%d")

        with open("expenses.csv", "a") as file:
            file.write(f"{date},{category},{subcategory},{amount}\n")

        result_label.config(text="✅ Expense Added!")

        entry_name.delete(0, tk.END)
        entry_category.delete(0, tk.END)
        entry_amount.delete(0, tk.END)

        save_btn.config(state="disabled")

    top = tk.Toplevel()
    top.title("Add Expense")
    top.geometry("300x250")

    tk.Label(top, text="Name").grid(row=0, column=0, padx=10, pady=10)
    entry_name = tk.Entry(top)
    entry_name.grid(row=0, column=1)

    tk.Label(top, text="Category").grid(row=1, column=0, padx=10, pady=10)
    entry_category = tk.Entry(top)
    entry_category.grid(row=1, column=1)

    tk.Label(top, text="Amount").grid(row=2, column=0, padx=10, pady=10)
    entry_amount = tk.Entry(top)
    entry_amount.grid(row=2, column=1)

    save_btn = tk.Button(top, text="Save", command=save_data)
    save_btn.grid(row=3, columnspan=2, pady=10)

    result_label = tk.Label(top, text="")
    result_label.grid(row=4, columnspan=2)

def view_analysis():
    try:
        with open("expenses.csv", "r") as file:
            lines = file.readlines()
    except:
        lines = []

    data = []

    for line in lines:
        parts = line.strip().split(",")

        data.append({
            "date": parts[0],
            "name": parts[1],
            "category": parts[2],
            "amount": float(parts[3])
        })

    # New window
    top = tk.Toplevel()
    top.title("Analysis")
    top.geometry("350x400")

    output = ""

    if len(data) == 0:
        output = "No data available"
    else:
        total = sum(item["amount"] for item in data)
        output += f"Total Expense: ₹{total}\n\n"

        category_total = {}

        for item in data:
            cat = item["category"]
            category_total[cat] = category_total.get(cat, 0) + item["amount"]

        output += "Category-wise:\n"
        for cat, amt in category_total.items():
            output += f"{cat} : ₹{amt}\n"

        # Insights
        if category_total:
            highest = max(category_total, key=category_total.get)
            output += f"\n🔍 Highest: {highest}\n"

        for cat, amt in category_total.items():
            percent = (amt / total) * 100
            if percent > 40:
                output += f"⚠️ High spending on {cat}\n"

        if len(data) < 3:
            output += "⚠️ Not enough data\n"

    tk.Label(top, text=output, justify="left").pack(pady=10)

# iske baad GUI start hoga
root = tk.Tk()
root.title("Expense Tracker")
root.geometry("300x250")

label = tk.Label(root, text="Expense Tracker", font=("Arial", 16))
label.pack(pady=10)

btn1 = tk.Button(root, text="Add Expense", width=20, command=add_expense)
btn1.pack(pady=5)

btn2 = tk.Button(root, text="View Analysis", width=20, command=view_analysis)
btn2.pack(pady=5)

btn3 = tk.Button(root, text="Exit", width=20, command=root.quit)
btn3.pack(pady=5)

root.mainloop()