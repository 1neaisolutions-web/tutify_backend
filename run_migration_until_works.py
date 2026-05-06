"""Run migration with retries until it succeeds."""
import subprocess
import sys
import time
import os

# Set encoding
os.environ['PYTHONIOENCODING'] = 'utf-8'

# Get the venv python path
VENV_PYTHON = os.path.join(os.path.dirname(__file__), 'venv', 'Scripts', 'python.exe')
if not os.path.exists(VENV_PYTHON):
    VENV_PYTHON = 'python'  # Fallback

def run_command(cmd, max_retries=10, retry_delay=3):
    """Run command with retries."""
    for attempt in range(1, max_retries + 1):
        print(f"\n{'='*70}")
        print(f"Attempt {attempt}/{max_retries}: Running migration...")
        print(f"{'='*70}\n")
        
        try:
            # Run the command with timeout
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120,  # 2 minute timeout
                encoding='utf-8',
                errors='replace'
            )
            
            # Print output
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            
            if result.returncode == 0:
                print(f"\n{'='*70}")
                print("SUCCESS! Migration completed!")
                print(f"{'='*70}\n")
                return True
            else:
                print(f"\nAttempt {attempt} failed with return code {result.returncode}")
                if attempt < max_retries:
                    print(f"Waiting {retry_delay} seconds before retry...")
                    time.sleep(retry_delay)
                else:
                    print(f"\n{'='*70}")
                    print("FAILED after all retries")
                    print(f"{'='*70}\n")
                    return False
                    
        except subprocess.TimeoutExpired:
            print(f"\nAttempt {attempt} timed out after 120 seconds")
            if attempt < max_retries:
                print(f"Waiting {retry_delay} seconds before retry...")
                time.sleep(retry_delay)
            else:
                print(f"\n{'='*70}")
                print("FAILED: Migration timed out after all retries")
                print(f"{'='*70}\n")
                return False
                
        except Exception as e:
            print(f"\nAttempt {attempt} failed with exception: {e}")
            if attempt < max_retries:
                print(f"Waiting {retry_delay} seconds before retry...")
                time.sleep(retry_delay)
            else:
                print(f"\n{'='*70}")
                print(f"FAILED: {e}")
                print(f"{'='*70}\n")
                return False
    
    return False

if __name__ == "__main__":
    # Change to backend directory
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(backend_dir)
    
    print("="*70)
    print("MIGRATION RUNNER - WILL NOT STOP UNTIL IT WORKS")
    print("="*70)
    
    # First, check current status
    print("\n1. Checking current migration status...")
    subprocess.run(
        f'"{VENV_PYTHON}" -m alembic current',
        shell=True,
        timeout=30
    )
    
    # Try to merge heads first if needed
    print("\n2. Checking for multiple heads...")
    result = subprocess.run(
        f'"{VENV_PYTHON}" -m alembic heads',
        shell=True,
        capture_output=True,
        text=True,
        timeout=30
    )
    
    heads = [h.strip() for h in result.stdout.strip().split('\n') if h.strip()]
    if len(heads) > 1:
        print(f"   Found {len(heads)} heads, attempting to merge...")
        # Create a merge migration
        head_revs = [h.split()[0] for h in heads if h.strip()]
        merge_cmd = f'"{VENV_PYTHON}" -m alembic merge -m "merge_heads" {" ".join(head_revs)}'
        print(f"   Running: {merge_cmd}")
        subprocess.run(merge_cmd, shell=True, timeout=60)
    
    # Now run the upgrade
    print("\n3. Running migration upgrade...")
    success = run_command(
        f'"{VENV_PYTHON}" -m alembic upgrade head',
        max_retries=30,  # Keep trying more times
        retry_delay=3
    )
    
    if success:
        print("\n4. Verifying migration...")
        subprocess.run(
            f'"{VENV_PYTHON}" -m alembic current',
            shell=True,
            timeout=30
        )
        sys.exit(0)
    else:
        print("\nMigration failed after all retries.")
        sys.exit(1)
