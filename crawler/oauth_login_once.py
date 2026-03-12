#!/usr/bin/env python3
"""One-time OAuth login script - Run this ONCE before starting workers"""
import os
from dotenv import load_dotenv
from helper.browser_helper import create_driver, human_delay
from helper.auth_helper import save_cookies

load_dotenv()

def main():
    print("="*60)
    print("LINKEDIN OAUTH LOGIN - ONE TIME SETUP")
    print("="*60)
    print("\nIni script untuk login OAuth SEKALI AJA.")
    print("Setelah login, cookie akan disimpan.")
    print("Semua worker nanti akan pake cookie ini.\n")
    
    # Check if cookies already exist
    if os.path.exists("data/cookie/.linkedin_cookies.json"):
        print("⚠️  Cookie sudah ada!")
        overwrite = input("Login ulang dan overwrite cookie? (y/n): ")
        if overwrite.lower() != 'y':
            print("Cancelled. Gunakan cookie yang ada.")
            return
    
    print("\n→ Membuka browser...")
    driver = create_driver()
    
    try:
        print("→ Membuka LinkedIn login page...")
        driver.get('https://www.linkedin.com/login')
        human_delay(2, 3)
        
        print("\n" + "="*60)
        print("SILAKAN LOGIN DENGAN OAUTH")
        print("="*60)
        print("1. Klik tombol 'Sign in with Google' (atau Microsoft/Apple)")
        print("2. Login dengan akun OAuth Anda")
        print("3. Tunggu sampai masuk ke LinkedIn feed/homepage")
        print("4. Kembali ke terminal ini dan tekan ENTER")
        print("="*60 + "\n")
        
        input("Tekan ENTER setelah berhasil login dan melihat feed...")
        
        # Verify login
        current_url = driver.current_url
        print(f"\n→ Current URL: {current_url}")
        
        if 'feed' in current_url or 'mynetwork' in current_url or '/in/' in current_url:
            print("✅ Login berhasil!")
            save_cookies(driver)
            print("\n" + "="*60)
            print("SETUP SELESAI!")
            print("="*60)
            print("Cookie tersimpan di: data/cookie/.linkedin_cookies.json")
            print("\nSekarang Anda bisa jalankan crawler:")
            print("  python crawler_consumer.py")
            print("\nSemua worker akan otomatis pake cookie ini.")
            print("="*60)
        else:
            print("⚠️  URL tidak seperti LinkedIn feed.")
            retry = input("Apakah Anda yakin sudah login? (y/n): ")
            if retry.lower() == 'y':
                save_cookies(driver)
                print("✅ Cookie disimpan.")
            else:
                print("❌ Login dibatalkan. Coba lagi.")
    
    finally:
        print("\n→ Menutup browser...")
        driver.quit()


if __name__ == "__main__":
    main()
