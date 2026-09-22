"""Prepara la directory di run per il nuovo calibrazione lbp_calibration_100."""
import shutil
from pathlib import Path

RUN_DIR = Path("cascade/run/lbp_calibration_100")
BACKUP_NAME = "outcomes_BACKUP_72.jsonl"

def main():
    print(f"=== PREPARAZIONE DIRECTORY: {RUN_DIR} ===")
    
    if not RUN_DIR.exists():
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        print("💡 Directory creata (non esisteva)")
        return 0
    
    # 1. Salva il backup del log esistente se non già presente
    log_path = RUN_DIR / "outcomes.jsonl"
    backup_path = RUN_DIR / BACKUP_NAME
    
    if log_path.exists() and not backup_path.exists():
        shutil.copy2(log_path, backup_path)
        print(f"✓ Backup creato: {BACKUP_NAME} ({log_path.stat().st_size} bytes)")
    elif backup_path.exists():
        print(f"✓ Backup già presente: {BACKUP_NAME}")
    
    # 2. Cancella action files e lbp_memory
    actions_dir = RUN_DIR / "actions"
    if actions_dir.exists():
        for f in actions_dir.glob("*.json"):
            f.unlink()
        print(f"✓ Azioni cancellate: {len(list(actions_dir.glob('*.json')))} file rimossi")
    
    memory_dir = RUN_DIR / "lbp_memory"
    if memory_dir.exists():
        shutil.rmtree(memory_dir)
        print("✓ Memoria lbp_memory rimossa")
    
    # 3. Cancella il log corrente (lo abbiamo già backup)
    if log_path.exists():
        log_path.unlink()
        print("✓ Log outcomes.jsonl rimosso (backup conservato)")
    
    print("✓ Directory pronta per nuovo run")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())