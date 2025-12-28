import time
import subprocess
import os
import logging

def is_ffmpeg_installed():
    """Preveri, če je ffmpeg nameščen."""
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except FileNotFoundError:
        return False

def remove(file):
    """Varno odstrani datoteko ali direktorij."""
    
    if os.path.isdir(file):
        logging.error(f"❌ Napaka pri brisanju {file}. To je mapa in ne datoteka.")
    else:
        try:
            os.remove(file)  # Odstrani posamezno datoteko
        except PermissionError:
            time.sleep(1)
            try:
                os.remove(file)
            except PermissionError:
                logging.error(f"❌ Napaka pri brisanju {file}. Poskusi ročno odstraniti.")
            