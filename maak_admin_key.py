"""
MAAKTHUNDER Studios — Admin Master License & Customer Manager
"""

import sys
import os
import json
import time
import argparse
import urllib.request
import pk_license_engine

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ID = "maakthunder-studio"

def get_admin_token():
    """Retrieves authenticated Firebase Admin token from configstore."""
    cfg_path = os.path.expanduser("~/.config/configstore/firebase-tools.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                d = json.load(f)
                return d.get("tokens", {}).get("access_token")
        except Exception:
            pass
    return None

def print_banner():
    print("=" * 65)
    print("   👑 MAAKTHUNDER STUDIOS — ADMIN MASTER LICENSE MANAGER")
    print("=" * 65)

def list_all_customers():
    token = get_admin_token()
    if not token:
        print("[!] Admin token not found. Please log in via Firebase CLI.")
        return

    url = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents/pk_licenses"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            docs = data.get("documents", [])
            print(f"\n📋 ALL REGISTERED CUSTOMERS ({len(docs)} Active Records):\n")
            print(f"{'NAME':<20} | {'PLAN':<10} | {'DAYS':<8} | {'EMAIL':<30} | {'LICENSE KEY'}")
            print("-" * 110)
            now_ts = int(time.time())
            for d in docs:
                fields = d.get("fields", {})
                name = fields.get("name", {}).get("stringValue", "User")[:18]
                email = fields.get("email", {}).get("stringValue", "-")[:28]
                plan = fields.get("plan", {}).get("stringValue", "trial").upper()[:8]
                key = fields.get("key", {}).get("stringValue", "-")
                expires_at = int(fields.get("expires_at", {}).get("integerValue", 0))
                days_left = max(0, int((expires_at - now_ts) // 86400)) if expires_at > now_ts else 0

                print(f"{name:<20} | {plan:<10} | {days_left:<4} d   | {email:<30} | {key}")
            print("\n" + "=" * 110 + "\n")
    except Exception as e:
        print(f"[ERROR] Could not fetch customer list: {e}")

def main():
    parser = argparse.ArgumentParser(description="MAAKTHUNDER Studios License Manager")
    parser.add_argument("--list", action="store_true", help="List all customers and their plans")
    parser.add_argument("--create", action="store_true", help="Generate a new license")
    parser.add_argument("--lookup", action="store_true", help="Lookup license by Email or Key")
    parser.add_argument("--extend", action="store_true", help="Extend an existing license duration")
    parser.add_argument("--upgrade", action="store_true", help="Upgrade customer to a higher tier")

    parser.add_argument("--id", type=str, help="License Key or Email address")
    parser.add_argument("--name", type=str, default="VIP Member", help="Customer name / gamer tag")
    parser.add_argument("--email", type=str, help="Customer email address")
    parser.add_argument("--plan", type=str, default="pro_plus", choices=["trial", "basic", "pro", "pro_plus", "annual", "lifetime"])
    parser.add_argument("--days", type=int, help="Days to add (positive) or reduce (negative)")
    parser.add_argument("--exact-days", type=int, help="Set exact remaining validity in days")

    args = parser.parse_args()

    # If no flags passed, launch interactive prompt menu
    if len(sys.argv) == 1:
        print_banner()
        while True:
            print("1. 📋 View All Customers & Plans")
            print("2. ⚡ Generate Free VIP / Gift License Key")
            print("3. 🔍 Search Customer by Email or Key")
            print("4. 🔄 Upgrade / Extend Customer Plan for Free")
            print("5. ❌ Exit")
            choice = input("\nSelect an option [1-5]: ").strip()

            if choice == "1":
                list_all_customers()
            elif choice == "2":
                name = input("Customer Name / Gamer Tag: ").strip() or "VIP Member"
                email = input("Customer Email: ").strip()
                if not email:
                    print("[!] Email is required.")
                    continue
                print("Plans: [1] Pro+ (Default)  [2] Pro  [3] Basic  [4] Lifetime")
                p_choice = input("Select Plan [1-4, Default 1]: ").strip()
                plan = "pro_plus" if p_choice == "1" else ("pro" if p_choice == "2" else ("basic" if p_choice == "3" else ("lifetime" if p_choice == "4" else "pro_plus")))
                days_input = input("Validity in Days [Default: 30, or 3650 for Lifetime]: ").strip()
                days = int(days_input) if days_input.isdigit() else (3650 if plan == "lifetime" else 30)

                print(f"\n[*] Issuing FREE {plan.upper()} License ({days} Days)...")
                res = pk_license_engine.register_or_upgrade_license(name, email, plan, tid="", duration_days=days)
                if res.get("success"):
                    print("\n" + "★" * 50)
                    print("  ✓ FREE LICENSE GENERATED SUCCESSFULLY!")
                    print(f"  Customer: {name} <{email}>")
                    print(f"  Plan:     {plan.upper()}")
                    print(f"  Days:     {res['days_left']} Days")
                    print(f"  KEY:      {res['license_key']}")
                    print("★" * 50 + "\n")
                else:
                    print("[ERROR]", res.get("error"))

            elif choice == "3":
                ident = input("Enter License Key or Email to search: ").strip()
                if ident:
                    info = pk_license_engine.lookup_license_by_identifier(ident)
                    if info.get("found"):
                        print("\n[CUSTOMER FOUND]")
                        print(f"  Name:       {info.get('name')}")
                        print(f"  Email:      {info.get('email')}")
                        print(f"  Key:        {info.get('key')}")
                        print(f"  Plan:       {info.get('plan', '').upper()}")
                        print(f"  Days Left:  {info.get('days_left')} Days")
                        print(f"  HWID Lock:  {info.get('hwid') or 'Unbound (Locks to first PC)'}\n")
                    else:
                        print("[!] Not found:", info.get("message"))

            elif choice == "4":
                ident = input("Enter Customer Email or Key to upgrade/extend: ").strip()
                if ident:
                    info = pk_license_engine.lookup_license_by_identifier(ident)
                    if not info.get("found"):
                        print("[!] Customer not found.")
                        continue
                    current_plan = str(info.get('plan', 'pro_plus')).upper()
                    current_days = info.get('days_left', 0)
                    print("\n" + "=" * 55)
                    print(f"  CUSTOMER FOUND: {info.get('name', 'User')} <{info.get('email')}>")
                    print(f"  Key:        {info.get('key')}")
                    print(f"  Plan:       {current_plan} ({current_days} Days Left)")
                    print(f"  HWID:       {info.get('hwid') or 'Unbound (Locks to first PC)'}")
                    print("=" * 55)

                    print("\nSelect Tier:")
                    print("  [1] Pro+ Studio Tier (Ultimate)")
                    print("  [2] Pro Tier (Creator)")
                    print("  [3] Basic Tier (Casual)")
                    print("  [4] Lifetime VIP (Permanent)")
                    print(f"  [5] Keep Current Tier ({current_plan})")
                    p_sel = input("Choose Tier [1-5, Default 5]: ").strip()
                    if p_sel == "1":
                        plan = "pro_plus"
                    elif p_sel == "2":
                        plan = "pro"
                    elif p_sel == "3":
                        plan = "basic"
                    elif p_sel == "4":
                        plan = "lifetime"
                    else:
                        plan = info.get("plan", "pro_plus")

                    duration_days = None
                    exact_days = None

                    if plan == "lifetime":
                        exact_days = 3650
                    else:
                        print("\nAdjust Validity / Days:")
                        print("  [1] Add +30 Days")
                        print("  [2] Add +60 Days")
                        print("  [3] Add Custom Days (e.g. type +15, +45, +90)")
                        print("  [4] Decrease / Subtract Days (e.g. type 10 to subtract 10 days)")
                        print("  [5] Set Exact Total Days (e.g. type 45 to set exactly 45 days remaining)")
                        print("  [6] Keep Existing Days Without Change")
                        d_sel = input("Choose Option [1-6, Default 1]: ").strip()

                        if d_sel == "2":
                            duration_days = 60
                        elif d_sel == "3":
                            custom_add = input("Enter number of days to ADD [e.g. 15, 45, 90]: ").strip()
                            try:
                                duration_days = int(custom_add)
                            except ValueError:
                                duration_days = 30
                        elif d_sel == "4":
                            custom_sub = input("Enter number of days to DECREASE / SUBTRACT [e.g. 15]: ").strip()
                            try:
                                duration_days = -abs(int(custom_sub))
                            except ValueError:
                                duration_days = -15
                        elif d_sel == "5":
                            custom_exact = input("Enter EXACT total days remaining [e.g. 45]: ").strip()
                            try:
                                exact_days = max(0, int(custom_exact))
                            except ValueError:
                                exact_days = current_days
                        elif d_sel == "6":
                            exact_days = current_days
                        else:
                            duration_days = 30

                    res = pk_license_engine.register_or_upgrade_license(
                        name=info.get("name", "User"),
                        email=info.get("email"),
                        plan=plan,
                        tid="",
                        duration_days=duration_days,
                        exact_days=exact_days
                    )
                    if res.get("success"):
                        print("\n" + "★" * 55)
                        print("  ✓ LICENSE UPDATED SUCCESSFULLY!")
                        print(f"  Key:       {res['license_key']}")
                        print(f"  Plan:      {res['plan'].upper()}")
                        print(f"  Days Left: {res['days_left']} Days Remaining")
                        print("★" * 55 + "\n")
                    else:
                        print("[ERROR]", res.get("error"))

            elif choice == "5":
                break
        return

    print_banner()

    if args.list:
        list_all_customers()

    elif args.create:
        if not args.email:
            print("[ERROR] Please provide --email")
            sys.exit(1)
        days = args.days or (15 if args.plan == "trial" else 30)
        res = pk_license_engine.register_or_upgrade_license(args.name, args.email, args.plan, tid="", duration_days=days)
        print(json.dumps(res, indent=2))

    elif args.extend or args.upgrade:
        ident = args.id or args.email
        if not ident:
            print("[ERROR] Please provide --id <Key or Email>")
            sys.exit(1)
        info = pk_license_engine.lookup_license_by_identifier(ident)
        if not info.get("found"):
            print("[ERROR] Customer not found:", info.get("message"))
            sys.exit(1)
        plan = args.plan or info.get("plan", "pro_plus")
        exact_days = args.exact_days if hasattr(args, "exact_days") else None
        duration_days = args.days if exact_days is None else None
        if exact_days is None and duration_days is None:
            duration_days = 30
        res = pk_license_engine.register_or_upgrade_license(
            name=info.get("name", "User"),
            email=info.get("email"),
            plan=plan,
            tid="",
            duration_days=duration_days,
            exact_days=exact_days
        )
        print(json.dumps(res, indent=2))

    elif args.lookup:
        ident = args.id or args.email
        print(json.dumps(pk_license_engine.lookup_license_by_identifier(ident), indent=2))

if __name__ == "__main__":
    main()
