#!/usr/bin/env python3
"""
Deploy Behemoth cBot to cTrader Robots directory.
"""
import os
import shutil
import pathlib

# Configuration
SOURCE_FILE = "src/cbot/BehemothTradeManager.cs"
# cTrader creates a nested folder structure: Robots/Name/Name/Name.cs
DEST_DIR = os.path.expanduser("~/cAlgo/Sources/Robots/BehemothTradeManager/BehemothTradeManager")
DEST_FILE = os.path.join(DEST_DIR, "BehemothTradeManager.cs")

def deploy():
    print(f"Deploying cBot to: {DEST_DIR}")
    
    # Ensure source exists
    if not os.path.exists(SOURCE_FILE):
        print(f"Error: Source file {SOURCE_FILE} not found.")
        exit(1)
        
    # Create destination directory
    os.makedirs(DEST_DIR, exist_ok=True)
    
    # Copy file
    shutil.copy2(SOURCE_FILE, DEST_FILE)
    print(f"✅ Successfully deployed to {DEST_FILE}")
    print("👉 Open cTrader Automate to build and run the bot.")

if __name__ == "__main__":
    deploy()
