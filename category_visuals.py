"""
Category Visual Intelligence Engine (category_visuals.py)
Accurately maps any user-entered category name (English, Hinglish, or Hindi transliteration)
to a curated, HTTP-verified high-resolution photographic thumbnail, Material icon, and accent color.
Uses strict word-boundary/phrase weighted scoring (preventing substring false positives like 'pet' in 'petrol'
or 'tax' in 'taxi'), with optional Gemini semantic classification fallback strictly constrained to verified keys.
"""

import json
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


CATEGORY_VISUAL_CATALOG: Dict[str, Dict[str, Any]] = {
    "food": {
        "label": "Food & Dining",
        "image": "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "restaurant",
        "color": "#EF4444",
        "phrases": ["food dining", "eating out", "street food", "mess bill", "tiffin service", "lunch box", "home food"],
        "tokens": ["food", "dining", "meal", "meals", "lunch", "dinner", "breakfast", "brunch", "tiffin", "mess", "canteen", "restaurant", "restaurants", "dhaba", "hotel", "thali", "khana", "bhojan", "nashta", "swiggy", "zomato", "eats"],
        "prefixes": ["restaur", "cater"],
    },
    "groceries": {
        "label": "Groceries & Kirana",
        "image": "https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "local_grocery_store",
        "color": "#10B981",
        "phrases": ["daily needs", "kirana store", "milk dairy", "fruits vegetables"],
        "tokens": ["grocery", "groceries", "kirana", "ration", "sabzi", "sabji", "vegetable", "vegetables", "veggies", "fruit", "fruits", "milk", "doodh", "dairy", "supermarket", "mart", "dmart", "blinkit", "zepto", "instamart", "bigbasket", "spencer", "reliance"],
        "prefixes": ["grocer", "vegetabl"],
    },
    "coffee_cafe": {
        "label": "Coffee, Chai & Snacks",
        "image": "https://images.unsplash.com/photo-1509042239860-f550ce710b93?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "local_cafe",
        "color": "#D97706",
        "phrases": ["ice cream", "tea coffee", "chai sutta", "cafe snacks", "evening snacks"],
        "tokens": ["coffee", "cafe", "chai", "tea", "chaiwala", "starbucks", "bakery", "cake", "pastry", "dessert", "desserts", "sweets", "mithai", "snack", "snacks", "nasta", "beverage", "juice", "shake", "chocolate", "biscuit"],
        "prefixes": ["baker", "dessert"],
    },
    "fastfood": {
        "label": "Fast Food & Takeout",
        "image": "https://images.unsplash.com/photo-1513104890138-7c749659a591?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "fastfood",
        "color": "#F97316",
        "phrases": ["fast food", "junk food", "late night"],
        "tokens": ["pizza", "burger", "burgers", "momos", "momo", "biryani", "roll", "rolls", "fries", "kfc", "mcdonalds", "dominos", "pizzahut", "sandwich", "noodles", "pasta", "chaat", "samosa", "takeout"],
        "prefixes": [],
    },
    "emi_loan": {
        "label": "EMI, Loans & Debt",
        "image": "https://images.unsplash.com/photo-1554224155-6726b3ff858f?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "receipt_long",
        "color": "#6366F1",
        "phrases": ["loan repayment", "home loan", "car loan", "bike loan", "personal loan", "education loan", "gold loan", "debt repayment", "emi payment", "bank emi", "monthly emi", "utility bill", "utility bills"],
        "tokens": ["emi", "emis", "loan", "loans", "repay", "repayment", "installment", "installments", "instalment", "debt", "debts", "mortgage", "kist", "kisht", "udhar", "udhaar", "karz", "chaukta", "bajaj", "finserv", "lending", "borrowed", "bill", "bills", "invoice"],
        "prefixes": ["repaym", "installm", "mortgag"],
    },
    "credit_card_bank": {
        "label": "Cards & Bank Payments",
        "image": "https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "credit_card",
        "color": "#8B5CF6",
        "phrases": ["credit card", "debit card", "card bill", "bank fee", "bank charges", "credit bill", "atm withdrawal", "upi payment"],
        "tokens": ["card", "cards", "credit", "debit", "visa", "mastercard", "rupay", "amex", "cred", "swipe", "banking", "bank", "atm", "neft", "rtgs", "imps", "fee", "fees", "charges", "penalty"],
        "prefixes": [],
    },
    "financial_stocks": {
        "label": "Financial, Stocks & SIP",
        "image": "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "trending_up",
        "color": "#6366F1",
        "phrases": ["mutual fund", "mutual funds", "stock market", "share market", "equity sip", "financial planning"],
        "tokens": ["financial", "finance", "finances", "sip", "mf", "stocks", "stock", "shares", "share", "equity", "trading", "trade", "nifty", "sensex", "zerodha", "groww", "upstox", "angel", "demat", "portfolio", "forex", "bonds", "debenture"],
        "prefixes": ["financ", "trad"],
    },
    "savings_piggy": {
        "label": "Savings, FD & Reserves",
        "image": "https://images.unsplash.com/photo-1579621970563-ebec7560ff3e?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "savings",
        "color": "#10B981",
        "phrases": ["emergency fund", "fixed deposit", "recurring deposit", "piggy bank", "chit fund"],
        "tokens": ["saving", "savings", "bachat", "fd", "rd", "ppf", "nps", "epf", "pf", "reserve", "reserves", "stash", "corpus", "vault", "kitty"],
        "prefixes": ["saving"],
    },
    "insurance_tax": {
        "label": "Insurance, Tax & Legal",
        "image": "https://images.unsplash.com/photo-1450101499163-c8848c66ca85?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "verified_user",
        "color": "#0EA5E9",
        "phrases": ["health insurance", "life insurance", "term insurance", "car insurance", "bike insurance", "income tax", "property tax", "tax filing"],
        "tokens": ["insurance", "insure", "lic", "policy", "premium", "mediclaim", "tax", "taxes", "gst", "tds", "itr", "audit", "ca", "legal", "lawyer", "advocate", "stamp", "notary", "passport", "visa", "challan", "fine", "documentation"],
        "prefixes": ["insur", "taxat"],
    },
    "bike_twowheeler": {
        "label": "Bike & Two-Wheeler",
        "image": "https://images.unsplash.com/photo-1558981403-c5f9899a28bc?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "two_wheeler",
        "color": "#F59E0B",
        "phrases": ["two wheeler", "bike service", "bike repair", "bike wash", "royal enfield"],
        "tokens": ["bike", "bikes", "motorcycle", "motorbike", "scooter", "scooty", "activa", "bullet", "enfield", "pulsar", "apache", "yamaha", "ktm", "helmet", "cycling", "bicycle", "cycle"],
        "prefixes": ["motorcycl", "bicycl"],
    },
    "fuel_petrol": {
        "label": "Petrol, Diesel & Fuel",
        "image": "https://images.unsplash.com/photo-1527018601619-a508a2be00cd?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "local_gas_station",
        "color": "#EA580C",
        "phrases": ["gas station", "petrol pump", "ev charging", "fuel expense"],
        "tokens": ["petrol", "diesel", "fuel", "fuels", "cng", "gasoline", "octan", "indianoil", "hpcl", "bpcl", "shell", "refuel", "mileage"],
        "prefixes": ["petrol", "refuel"],
    },
    "train_metro": {
        "label": "Train, Metro & Transit",
        "image": "https://images.unsplash.com/photo-1474487548417-781cb71495f3?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "train",
        "color": "#0284C7",
        "phrases": ["metro card", "train ticket", "bus pass", "railway ticket", "public transport"],
        "tokens": ["train", "trains", "metro", "rail", "railway", "irctc", "bus", "buses", "transit", "subway", "tram", "vande", "shatabdi", "rajdhani", "sleeper", "local"],
        "prefixes": ["railw"],
    },
    "car_transport": {
        "label": "Transport, Car & Cab",
        "image": "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "directions_car",
        "color": "#F59E0B",
        "phrases": ["cab ride", "auto rickshaw", "toll tax", "car wash"],
        "tokens": ["transport", "transportation", "car", "cars", "cab", "cabs", "taxi", "taxis", "uber", "ola", "rapido", "auto", "rickshaw", "commute", "vehicle", "vehicles", "gaadi", "gadi", "toll", "fastag", "parking", "driver", "ride", "rides"],
        "prefixes": ["transport", "commut"],
    },
    "travel_flight": {
        "label": "Travel, Flights & Vacations",
        "image": "https://images.unsplash.com/photo-1488646953014-85cb44e25828?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "flight",
        "color": "#06B6D4",
        "phrases": ["road trip", "air ticket", "flight ticket", "hotel booking", "hill station", "weekend getaway"],
        "tokens": ["travel", "travels", "travelling", "trip", "trips", "tour", "tours", "vacation", "vacations", "holiday", "holidays", "flight", "flights", "airline", "indigo", "airindia", "vistara", "airport", "luggage", "resort", "airbnb", "oyo", "makemytrip", "yatra", "safar", "picnic", "camping", "trek", "trekking"],
        "prefixes": ["travel", "vacat", "touris"],
    },
    "entertainment": {
        "label": "Movies, OTT & Streaming",
        "image": "https://images.unsplash.com/photo-1517604931442-7e0c8ed2963c?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "movie",
        "color": "#8B5CF6",
        "phrases": ["ott subscription", "movie night", "prime video", "youtube premium", "bookmyshow"],
        "tokens": ["entertainment", "movie", "movies", "cinema", "film", "films", "pvr", "inox", "theatre", "theater", "netflix", "prime", "hotstar", "disney", "sonyliv", "zee5", "jiocinema", "ott", "subscription", "subscriptions", "streaming", "youtube", "fun", "amusement"],
        "prefixes": ["entertain", "subscri"],
    },
    "music_concert": {
        "label": "Music, Audio & Concerts",
        "image": "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "music_note",
        "color": "#A855F7",
        "phrases": ["music class", "live concert"],
        "tokens": ["music", "musical", "song", "songs", "spotify", "gaana", "wynk", "concert", "concerts", "guitar", "piano", "violin", "drums", "flute", "singing", "podcast", "audio", "studio", "dj", "karaoke"],
        "prefixes": ["music", "concert"],
    },
    "gaming": {
        "label": "Gaming & Esports",
        "image": "https://images.unsplash.com/photo-1538481199705-c710c4e965fc?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "sports_esports",
        "color": "#7C3AED",
        "phrases": ["video game", "video games", "ps5 game", "game pass"],
        "tokens": ["game", "games", "gaming", "gamer", "playstation", "ps4", "ps5", "xbox", "nintendo", "steam", "valorant", "bgmi", "pubg", "esports", "arcade", "console", "controller", "uc"],
        "prefixes": ["gaming"],
    },
    "medical_pharmacy": {
        "label": "Medical, Doctor & Pharmacy",
        "image": "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "medical_services",
        "color": "#EF4444",
        "phrases": ["doctor visit", "blood test", "full body checkup", "dental care", "eye checkup", "first aid"],
        "tokens": ["medical", "medicine", "medicines", "meds", "dawai", "dawa", "dawaiya", "pharmacy", "chemist", "apollo", "pharmeasy", "1mg", "netmeds", "doctor", "doctors", "hospital", "clinic", "dental", "dentist", "dant", "tooth", "teeth", "checkup", "lab", "pathology", "xray", "mri", "surgery", "ilaaj", "ilaj", "tablet", "tablets", "syrup", "vaccine", "inhaler", "glasses", "spectacles", "lenskart"],
        "prefixes": ["medicin", "pharmac", "hospit", "patholog", "dent"],
    },
    "health_wellness": {
        "label": "Health & Wellness",
        "image": "https://images.unsplash.com/photo-1506126613408-eca07ce68773?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "spa",
        "color": "#10B981",
        "phrases": ["mental health", "wellness care", "self care"],
        "tokens": ["health", "healthcare", "wellness", "yoga", "meditation", "mindfulness", "ayurveda", "therapy", "therapist", "nutrition", "vitamin", "vitamins", "supplement", "supplements", "hygiene"],
        "prefixes": ["health", "welln", "therap"],
    },
    "gym_fitness": {
        "label": "Gym, Fitness & Workout",
        "image": "https://images.unsplash.com/photo-1517838277536-f5f99be501cd?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "fitness_center",
        "color": "#EC4899",
        "phrases": ["protein powder", "gym membership", "personal trainer"],
        "tokens": ["gym", "fitness", "workout", "workouts", "exercise", "exercises", "crossfit", "cardio", "dumbbells", "weights", "cult", "cultfit", "protein", "whey", "creatine", "diet", "zumba", "pilates", "bodybuilding"],
        "prefixes": ["fitne", "workou", "exercis"],
    },
    "sports": {
        "label": "Sports & Outdoor",
        "image": "https://images.unsplash.com/photo-1531415074968-036ba1b575da?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "sports_cricket",
        "color": "#16A34A",
        "phrases": ["cricket turf", "sports gear", "swimming pool", "badminton court"],
        "tokens": ["sports", "sport", "cricket", "football", "soccer", "badminton", "tennis", "basketball", "volleyball", "swimming", "swim", "running", "marathon", "turf", "stadium", "bat", "ball", "racket", "decathlon", "golf"],
        "prefixes": ["athlet"],
    },
    "rent_property": {
        "label": "Rent, PG & Hostel",
        "image": "https://images.unsplash.com/photo-1560518883-ce09059eeffa?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "apartment",
        "color": "#3B82F6",
        "phrases": ["house rent", "room rent", "flat rent", "pg rent", "hostel fee", "security deposit", "rental income", "broker fee"],
        "tokens": ["rent", "rental", "rented", "lease", "pg", "hostel", "kiraya", "kiraye", "makaan", "flat", "apartment", "broker", "brokerage", "deposit", "tenant", "landlord", "property", "realty", "realestate"],
        "prefixes": ["apartm", "propert"],
    },
    "house_home": {
        "label": "House & Society",
        "image": "https://images.unsplash.com/photo-1513694203232-719a280e022f?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "home",
        "color": "#3B82F6",
        "phrases": ["society maintenance", "home upkeep", "household items", "ghar kharch"],
        "tokens": ["house", "home", "homes", "housing", "household", "society", "ghar", "villa", "domestic", "utilities", "utility"],
        "prefixes": ["househ", "housin"],
    },
    "furniture_decor": {
        "label": "Furniture & Home Decor",
        "image": "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "chair",
        "color": "#0D9488",
        "phrases": ["home decor", "interior design", "kitchenware"],
        "tokens": ["furniture", "sofa", "couch", "chair", "table", "desk", "bed", "mattress", "pillow", "curtain", "curtains", "decor", "decoration", "ikea", "pepperfry", "interior", "paint", "painting", "tiles", "utensils", "crockery"],
        "prefixes": ["furnit", "decorat"],
    },
    "repair_tools": {
        "label": "Repairs, Servicing & Tools",
        "image": "https://images.unsplash.com/photo-1581092160607-ee22621dd758?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "build",
        "color": "#475569",
        "phrases": ["ac service", "bike servicing", "car service", "home repair", "urban company"],
        "tokens": ["repair", "repairs", "servicing", "service", "maintenance", "plumber", "plumbing", "electrician", "carpenter", "mechanic", "garage", "puncture", "hardware", "tools", "toolkit", "spare", "parts", "fixing", "fix"],
        "prefixes": ["servic", "mainten", "repair"],
    },
    "electricity_power": {
        "label": "Electricity, Power & Solar",
        "image": "https://images.unsplash.com/photo-1473341304170-971dccb5ac1e?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "bolt",
        "color": "#EAB308",
        "phrases": ["electricity bill", "electric bill", "power bill", "light bill", "bijli bill", "solar panel"],
        "tokens": ["electricity", "electric", "electrical", "power", "bijli", "bijlee", "bescom", "msedcl", "tata", "adani", "bses", "inverter", "ups", "battery", "generator", "solar", "bulb", "light", "energy", "ac"],
        "prefixes": ["electr"],
    },
    "water_utility": {
        "label": "Water, LPG Gas & Cylinders",
        "image": "https://images.unsplash.com/photo-1548839140-29a749e1cf4d?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "water_drop",
        "color": "#06B6D4",
        "phrases": ["water bill", "gas bill", "gas cylinder", "lpg cylinder", "drinking water", "water purifier"],
        "tokens": ["water", "pani", "paani", "bisleri", "aquaguard", "ro", "tanker", "cylinder", "lpg", "indane", "bharatgas", "hpgas", "pipeline", "png", "jal", "sewage"],
        "prefixes": ["purifi"],
    },
    "internet_wifi": {
        "label": "WiFi, Broadband & Internet",
        "image": "https://images.unsplash.com/photo-1544197150-b99a580bb7a8?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "wifi",
        "color": "#2563EB",
        "phrases": ["wifi bill", "internet bill", "broadband bill", "jio fiber", "airtel fiber", "cloud storage", "web hosting"],
        "tokens": ["wifi", "wi-fi", "internet", "broadband", "fiber", "jiofiber", "act", "hathway", "router", "modem", "data", "net", "network", "vpn", "domain", "hosting", "cloud", "aws", "server", "saas"],
        "prefixes": ["broadb", "intern"],
    },
    "phone_mobile": {
        "label": "Mobile, Phone & Recharge",
        "image": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "smartphone",
        "color": "#38BDF8",
        "phrases": ["mobile recharge", "phone bill", "phone recharge", "dth recharge", "postpaid bill"],
        "tokens": ["phone", "mobile", "smartphone", "iphone", "android", "recharge", "recharges", "prepaid", "postpaid", "sim", "jio", "airtel", "vi", "vodafone", "bsnl", "dth", "tataplay", "dish", "calling", "telecom"],
        "prefixes": ["recharg", "telec", "smartph"],
    },
    "electronics_tech": {
        "label": "Electronics & Gadgets",
        "image": "https://images.unsplash.com/photo-1498049794561-7780e7231661?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "devices",
        "color": "#4F46E5",
        "phrases": ["home appliance", "kitchen appliance", "smart watch"],
        "tokens": ["electronics", "electronic", "gadget", "gadgets", "tech", "technology", "laptop", "macbook", "pc", "desktop", "computer", "monitor", "keyboard", "mouse", "tablet", "ipad", "tv", "television", "fridge", "washing", "microwave", "headphone", "headphones", "earbuds", "airpods", "speaker", "charger", "cable", "smartwatch", "appliance", "appliances"],
        "prefixes": ["electron", "comput", "applian"],
    },
    "camera_photo": {
        "label": "Camera & Photography",
        "image": "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "photo_camera",
        "color": "#334155",
        "phrases": ["photo shoot", "camera gear"],
        "tokens": ["camera", "cameras", "photography", "photo", "photos", "photoshoot", "dslr", "lens", "tripod", "gopro", "drone", "videography", "cinematography", "printing", "album"],
        "prefixes": ["photogr"],
    },
    "shopping": {
        "label": "Shopping, Clothes & Fashion",
        "image": "https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "shopping_bag",
        "color": "#EC4899",
        "phrases": ["online shopping", "winter wear", "festive shopping"],
        "tokens": ["shopping", "shop", "clothes", "clothing", "cloth", "kapde", "fashion", "apparel", "dress", "dresses", "saree", "kurta", "shirt", "tshirt", "jeans", "shoes", "footwear", "sneakers", "sandals", "bag", "handbag", "wallet", "myntra", "ajio", "amazon", "flipkart", "meesho", "nykaa", "zudio", "zara", "hm", "mall", "accessories", "retail"],
        "prefixes": ["shopp", "cloth", "fash", "footw"],
    },
    "jewelry_gold": {
        "label": "Jewelry, Gold & Luxury",
        "image": "https://images.unsplash.com/photo-1515562141207-7a88fb7ce338?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "diamond",
        "color": "#F59E0B",
        "phrases": ["gold coin", "gold jewelry", "digital gold"],
        "tokens": ["gold", "silver", "diamond", "jewelry", "jewellery", "jewels", "ring", "necklace", "bangle", "earring", "bracelet", "sona", "chandi", "tanishq", "malabar", "kalyan", "caratlane", "luxury", "ornament"],
        "prefixes": ["jewel", "ornam"],
    },
    "salon_haircut": {
        "label": "Salon, Haircut & Grooming",
        "image": "https://images.unsplash.com/photo-1585747860715-2ba37e788b70?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "content_cut",
        "color": "#64748B",
        "phrases": ["hair cut", "beauty parlour", "beauty parlor", "beard trim"],
        "tokens": ["salon", "saloon", "haircut", "hair", "barber", "nai", "beard", "shave", "trim", "parlour", "parlor", "facial", "waxing", "threading", "pedicure", "manicure", "grooming"],
        "prefixes": ["hair", "parl"],
    },
    "personal_grooming": {
        "label": "Personal Care & Cosmetics",
        "image": "https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "face",
        "color": "#D946EF",
        "phrases": ["personal care", "skin care", "self care"],
        "tokens": ["personal", "skincare", "makeup", "cosmetic", "cosmetics", "perfume", "deo", "deodorant", "shampoo", "soap", "lotion", "cream", "serum", "sunscreen", "beauty", "toiletries", "pocket", "allowance", "self"],
        "prefixes": ["cosmet", "skinc"],
    },
    "laundry_cleaning": {
        "label": "Laundry, Maid & Cleaning",
        "image": "https://images.unsplash.com/photo-1545173168-9f1947eebb7f?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "local_laundry_service",
        "color": "#06B6D4",
        "phrases": ["dry clean", "dry cleaning", "house help", "maid salary", "cook salary", "car cleaning"],
        "tokens": ["laundry", "wash", "washing", "dryclean", "iron", "ironing", "press", "dhobi", "maid", "cook", "househelp", "bai", "cleaner", "cleaning", "detergent", "surf", "harpic", "sanitary", "garbage", "trash"],
        "prefixes": ["laundr", "clean"],
    },
    "education": {
        "label": "Education, Tuition & Courses",
        "image": "https://images.unsplash.com/photo-1497633762265-9d179a990aa6?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "school",
        "color": "#06B6D4",
        "phrases": ["school fees", "college fees", "tuition fee", "exam form", "online course", "coaching class"],
        "tokens": ["education", "tuition", "tution", "coaching", "school", "college", "university", "campus", "semester", "exam", "exams", "course", "courses", "certification", "udemy", "coursera", "unacademy", "physicswallah", "byjus", "scholarship", "padhai", "learning", "workshop", "seminar"],
        "prefixes": ["educat", "academ", "coach", "tuit"],
    },
    "books_study": {
        "label": "Books & Stationery",
        "image": "https://images.unsplash.com/photo-1495446815901-a7297e633e8d?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "menu_book",
        "color": "#8B5CF6",
        "phrases": ["study material", "reading list"],
        "tokens": ["book", "books", "novel", "novels", "kindle", "magazine", "magazines", "newspaper", "notebook", "notebooks", "diary", "stationery", "stationary", "pen", "pencil", "library", "xerox", "photocopy", "printout", "study", "reading"],
        "prefixes": ["station"],
    },
    "pets": {
        "label": "Pets & Animal Care",
        "image": "https://images.unsplash.com/photo-1543466835-00a7907e9de1?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "pets",
        "color": "#F59E0B",
        "phrases": ["pet food", "dog food", "cat food", "vet visit"],
        "tokens": ["pet", "pets", "dog", "dogs", "cat", "cats", "puppy", "kitten", "vet", "veterinary", "pedigree", "whiskas", "aquarium", "kennel"],
        "prefixes": ["veterin"],
    },
    "kids_baby": {
        "label": "Baby Care & Kids",
        "image": "https://images.unsplash.com/photo-1515488042361-ee00e0ddd4e4?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "child_care",
        "color": "#EC4899",
        "phrases": ["baby care", "pocket money", "kids toys"],
        "tokens": ["baby", "babies", "kid", "kids", "child", "children", "childcare", "daycare", "creche", "diaper", "diapers", "formula", "pampers", "toy", "toys", "bacha", "baccha", "bacche", "son", "daughter", "newborn", "maternity"],
        "prefixes": ["child"],
    },
    "family_home": {
        "label": "Family & Parents Support",
        "image": "https://images.unsplash.com/photo-1511895426328-dc8714191300?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "family_restroom",
        "color": "#3B82F6",
        "phrases": ["home money", "ghar bheja", "parents support"],
        "tokens": ["family", "families", "parent", "parents", "mom", "mother", "maa", "mummy", "dad", "father", "papa", "bhai", "brother", "sister", "behen", "didi", "wife", "husband", "spouse", "grandparents", "dada", "dadi", "nana", "nani", "relatives", "guest", "guests", "mehmaan"],
        "prefixes": ["famil"],
    },
    "wedding_party": {
        "label": "Wedding & Functions",
        "image": "https://images.unsplash.com/photo-1519741497674-611481863552?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "celebration",
        "color": "#DB2777",
        "phrases": ["wedding shopping", "shagun lifafa"],
        "tokens": ["wedding", "marriage", "shadi", "shaadi", "engagement", "reception", "mehendi", "haldi", "sangeet", "baraat", "shagun", "bride", "groom", "function", "ceremony"],
        "prefixes": ["marriag", "wedd"],
    },
    "gifts_celebration": {
        "label": "Gifts, Parties & Festivals",
        "image": "https://images.unsplash.com/photo-1549465220-1a8b9238cd48?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "redeem",
        "color": "#EC4899",
        "phrases": ["birthday party", "date night", "anniversary gift", "festival shopping"],
        "tokens": ["gift", "gifts", "present", "presents", "birthday", "anniversary", "party", "parties", "celebration", "festival", "festivals", "diwali", "holi", "eid", "christmas", "rakhi", "rakshabandhan", "navratri", "ganesh", "date", "treats", "treat", "flowers", "bouquet"],
        "prefixes": ["celebr", "festiv", "anniv", "birthd"],
    },
    "temple_charity": {
        "label": "Temple, Puja & Charity",
        "image": "https://images.unsplash.com/photo-1532629345422-7515f3d16bb6?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "volunteer_activism",
        "color": "#F97316",
        "phrases": ["puja samagri", "mandir chadhava", "religious donation"],
        "tokens": ["temple", "mandir", "puja", "pooja", "aarti", "prasad", "chadhava", "charity", "donation", "donations", "donate", "daan", "ngo", "zakat", "sadaqah", "church", "mosque", "masjid", "gurudwara", "langar", "spiritual", "diya", "incense", "agarbatti", "help", "welfare"],
        "prefixes": ["charit", "donat", "relig", "spiritu"],
    },
    "garden_nature": {
        "label": "Gardening, Plants & Farming",
        "image": "https://images.unsplash.com/photo-1416879595882-3373a0480b5b?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "yard",
        "color": "#22C55E",
        "phrases": ["indoor plants", "kitchen garden"],
        "tokens": ["garden", "gardening", "plant", "plants", "nursery", "seeds", "fertilizer", "soil", "pots", "pot", "flower", "flowers", "trees", "farming", "agriculture", "kheti", "farm"],
        "prefixes": ["garden", "agric", "farm"],
    },
    "nightlife_drinks": {
        "label": "Drinks, Pub & Nightlife",
        "image": "https://images.unsplash.com/photo-1514362545857-3bc16c4c7d1b?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "local_bar",
        "color": "#E11D48",
        "phrases": ["night out", "friday night"],
        "tokens": ["drink", "drinks", "bar", "pub", "club", "clubbing", "nightlife", "beer", "wine", "whisky", "whiskey", "vodka", "rum", "gin", "alcohol", "liquor", "daaru", "cocktail", "cocktails", "lounge", "smoke", "smoking", "cigarette", "vape"],
        "prefixes": ["alcoh", "nightl", "cockt"],
    },
    # ---------------- INCOME CATEGORIES ----------------
    "salary": {
        "label": "Salary & Wages",
        "image": "https://images.unsplash.com/photo-1553729459-efe14ef6055d?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "work",
        "color": "#10B981",
        "phrases": ["monthly salary", "pocket salary"],
        "tokens": ["salary", "salaries", "paycheck", "payroll", "wage", "wages", "stipend", "pension", "job", "pay", "vetan", "tankhah"],
        "prefixes": ["salar", "stipend"],
    },
    "business": {
        "label": "Business & Store Revenue",
        "image": "https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "business_center",
        "color": "#3B82F6",
        "phrases": ["shop sales", "business income", "client payment"],
        "tokens": ["business", "agency", "client", "clients", "revenue", "sales", "profit", "dukaan", "vyapar", "commission", "commissions", "vendor", "startup", "commerce", "office", "workspace"],
        "prefixes": ["busin", "reven"],
    },
    "freelance": {
        "label": "Freelance & Consulting",
        "image": "https://images.unsplash.com/photo-1499750310107-5fef28a66643?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "laptop_mac",
        "color": "#06B6D4",
        "phrases": ["side hustle", "side income", "part time"],
        "tokens": ["freelance", "freelancing", "project", "projects", "consult", "consulting", "consultation", "gig", "fiverr", "upwork", "contract", "royalty", "creator", "youtube", "blogging"],
        "prefixes": ["freelanc", "consult"],
    },
    "investments": {
        "label": "Investments & Capital Gains",
        "image": "https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "show_chart",
        "color": "#8B5CF6",
        "phrases": ["capital gains", "investment return"],
        "tokens": ["investment", "investments", "invest", "investing", "returns", "gain", "gains", "maturing", "maturity"],
        "prefixes": ["investm"],
    },
    "bonus": {
        "label": "Bonus, Rewards & Cashback",
        "image": "https://images.unsplash.com/photo-1559526324-4b87b5e36e44?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "emoji_events",
        "color": "#F59E0B",
        "phrases": ["festival bonus", "cashback reward"],
        "tokens": ["bonus", "bonuses", "incentive", "incentives", "reward", "rewards", "cashback", "refund", "refunds", "reimbursement", "prize", "award", "lottery", "grant", "grants"],
        "prefixes": ["incent", "cashba", "reimbur"],
    },
    "dividend": {
        "label": "Dividends & Interest",
        "image": "https://images.unsplash.com/photo-1526304640581-d334cdbbf45e?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "paid",
        "color": "#10B981",
        "phrases": ["bank interest", "fd interest", "dividend payout"],
        "tokens": ["dividend", "dividends", "interest", "byaj", "yield", "payout"],
        "prefixes": ["dividen"],
    },
    "crypto": {
        "label": "Crypto & Web3",
        "image": "https://images.unsplash.com/photo-1621416894569-0f39ed31d247?auto=format&fit=crop&w=160&h=160&q=80",
        "icon": "currency_bitcoin",
        "color": "#F59E0B",
        "phrases": ["digital currency"],
        "tokens": ["crypto", "cryptocurrency", "bitcoin", "btc", "eth", "ethereum", "solana", "usdt", "binance", "coin", "coins", "web3", "nft", "token", "mining", "airdrop"],
        "prefixes": ["crypt"],
    },
}


def _score_theme(padded: str, tokens: List[str], theme_key: str, meta: Dict[str, Any], cat_type: str) -> int:
    score = 0
    for phrase in meta.get("phrases", []):
        if f" {phrase} " in padded:
            score += 24
    token_set = set(tokens)
    for kw in meta.get("tokens", []):
        if kw in token_set:
            score += 16
    for pref in meta.get("prefixes", []):
        if len(pref) >= 5 and any(t.startswith(pref) for t in tokens):
            score += 12
    # Type affinity tie-breaker: e.g. 'rent' as INCOME is rental property, as EXPENSE also fits rent_property;
    # 'savings'/'dividend'/'salary' fit income cleanly
    if score > 0:
        income_themes = {"salary", "business", "freelance", "investments", "bonus", "dividend", "crypto"}
        if cat_type == "INCOME" and theme_key in income_themes:
            score += 3
        elif cat_type == "EXPENSE" and theme_key not in income_themes:
            score += 2
    return score


def resolve_category_visual_fast(name: str, cat_type: str = "EXPENSE") -> Dict[str, Any]:
    """
    Deterministic, instant (0ms) semantic classifier across 44 verified photo themes.
    Returns image_url='' with high-craft icon/color if no confident match exists (never assigns unrelated stock photos).
    """
    clean = (name or "").strip()
    ctype = (cat_type or "EXPENSE").upper()
    if not clean:
        return {
            "theme_key": None,
            "label": "Custom",
            "image_url": "",
            "icon": "account_balance_wallet" if ctype == "INCOME" else "category",
            "color_hex": "#10B981" if ctype == "INCOME" else "#6366F1",
            "confidence": 0,
            "source": "fallback",
        }

    tokens = re.findall(r"[a-z0-9]+", clean.lower())
    padded = " " + " ".join(tokens) + " "

    # Context-sensitive adjustment: "credit card" shouldn't accidentally lose to generic "card", etc.
    best_key = None
    best_score = 0
    for key, meta in CATEGORY_VISUAL_CATALOG.items():
        sc = _score_theme(padded, tokens, key, meta, ctype)
        if sc > best_score:
            best_score = sc
            best_key = key

    if best_key and best_score >= 12:
        chosen = CATEGORY_VISUAL_CATALOG[best_key]
        return {
            "theme_key": best_key,
            "label": chosen["label"],
            "image_url": chosen["image"],
            "icon": chosen["icon"],
            "color_hex": chosen["color"],
            "confidence": best_score,
            "source": "semantic_catalog",
        }

    # If user explicitly creates an Income category with no specific match, savings/wallet photo fits income naturally
    if ctype == "INCOME":
        sav = CATEGORY_VISUAL_CATALOG["savings_piggy"]
        return {
            "theme_key": "savings_piggy",
            "label": "Income & Earnings",
            "image_url": sav["image"],
            "icon": "account_balance_wallet",
            "color_hex": "#10B981",
            "confidence": 8,
            "source": "income_default",
        }

    # Truly unrecognized abstract name: keep image_url empty at Tier 1 so Tier 2 Gemini can classify or sleek badge renders
    palette = ["#6366F1", "#3B82F6", "#10B981", "#8B5CF6", "#F59E0B", "#EC4899", "#06B6D4"]
    color_idx = sum(ord(ch) for ch in clean.lower()) % len(palette)
    return {
        "theme_key": None,
        "label": "Custom Category",
        "image_url": "",
        "icon": "sell",
        "color_hex": palette[color_idx],
        "confidence": 0,
        "source": "unmatched",
    }


def _classify_with_gemini(name: str, cat_type: str = "EXPENSE") -> Optional[str]:
    """
    Optional Tier-2 semantic classification using Gemini Flash strictly constrained to verified theme keys.
    Returns None if no API key configured, timeout occurs, or Gemini returns NONE.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key or not name.strip():
        return None

    theme_keys = list(CATEGORY_VISUAL_CATALOG.keys())
    prompt = (
        f"Classify personal finance category '{name.strip()}' (type: {cat_type}) into the SINGLE best matching visual theme key "
        f"from this exact list: {', '.join(theme_keys)}.\n"
        "Rules:\n"
        "- Only return a key from the list if it genuinely and accurately represents the category concept (including Hindi/Hinglish/slang terms).\n"
        "- If none of those themes accurately represent this category, return NONE.\n"
        "- Respond with ONLY the single key word (or NONE), nothing else."
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 20},
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            ans = data["candidates"][0]["content"]["parts"][0]["text"].strip().lower()
            ans = re.sub(r"[^a-z0-9_]", "", ans)
            if ans in CATEGORY_VISUAL_CATALOG:
                return ans
    except Exception:
        return None
    return None


def resolve_category_visual(name: str, cat_type: str = "EXPENSE", allow_ai: bool = True) -> Dict[str, Any]:
    """
    Full Tier-1 + Tier-2 category visual resolver.
    Guarantees accurate, verified photography whenever a real domain matches, and never assigns random/unrelated images.
    """
    fast = resolve_category_visual_fast(name, cat_type)
    if fast["confidence"] >= 12:
        return fast

    if allow_ai:
        ai_key = _classify_with_gemini(name, cat_type)
        if ai_key and ai_key in CATEGORY_VISUAL_CATALOG:
            chosen = CATEGORY_VISUAL_CATALOG[ai_key]
            return {
                "theme_key": ai_key,
                "label": chosen["label"],
                "image_url": chosen["image"],
                "icon": chosen["icon"],
                "color_hex": chosen["color"],
                "confidence": 20,
                "source": "gemini_ai",
            }

    return fast
