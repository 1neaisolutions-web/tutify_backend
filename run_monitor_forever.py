"""
Run Monitor Forever - NEVER STOPS, reports every step, fixes issues automatically.
"""
import subprocess
import sys
import os

# Run monitor_and_fix.py in a loop that never stops
script_path = os.path.join(os.path.dirname(__file__), "monitor_and_fix.py")

print("="*70)
print("STARTING CONTINUOUS MONITOR - NEVER STOPS")
print("="*70)
print("This will run monitor_and_fix.py continuously")
print("It will report every step: OCR, Chunking, Embedding, Indexing")
print("It will fix issues automatically and continue until document is ready")
print("="*70)
print()

while True:
    try:
        # Run the monitor script
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=os.path.dirname(__file__),
            capture_output=False,
            text=True
        )
        
        # If it exits with 0, document is ready
        if result.returncode == 0:
            print("\n" + "="*70)
            print("DOCUMENT IS READY - MONITORING COMPLETE")
            print("="*70)
            break
        else:
            # If it fails, restart immediately
            print("\n[WARN] Monitor script exited, restarting in 5 seconds...")
            import time
            time.sleep(5)
            continue
            
    except KeyboardInterrupt:
        print("\n\n[INFO] Stopped by user")
        break
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        print("[INFO] Restarting in 10 seconds...")
        import time
        time.sleep(10)
        continue
