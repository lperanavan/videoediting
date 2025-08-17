import os
import json
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
from pathlib import Path
import time

from premiere_automation import PremiereAutomation
from tape_detector import TapeDetector
from gdrive_handler import GDriveHandler

VIDEO_EXTENSIONS = ['.mp4', '.avi', '.mov', '.mkv']
PROCESSED_FOLDER_NAME = "processed"

def is_video_file(fname):
    return any(fname.lower().endswith(ext) for ext in VIDEO_EXTENSIONS)

def wait_for_download(filename, folder):
    """Wait until file stops growing (download complete)."""
    path = os.path.join(folder, filename)
    last_size = -1
    while True:
        if os.path.exists(path):
            size = os.path.getsize(path)
            if size == last_size:  # file size stable
                break
            last_size = size
        time.sleep(2)

def detect_tape_type(filename):
    tape_types = ['VHS', 'MiniDV', 'Hi8', 'Betamax', 'Digital8', 'Super8']
    tape_from_name = None
    for tape in tape_types:
        if tape.lower() in filename.lower():
            tape_from_name = tape
            break
    if tape_from_name:
        return tape_from_name
    root = tk.Tk()
    root.withdraw()
    return simpledialog.askstring("Tape Type", f"Enter tape type for {filename} (e.g., VHS, MiniDV):")

def process_video(video_path, tape_type, output_folder, premiere):
    processed_files = premiere.process_videos([video_path], tape_type, output_folder)
    return processed_files[0] if processed_files else None

def export_video(original_path, output_folder):
    folder, fname = os.path.split(original_path)
    name, ext = os.path.splitext(fname)
    new_name = f"{name}-edited{ext}"
    os.makedirs(output_folder, exist_ok=True)
    output_path = os.path.join(output_folder, new_name)
    if os.path.exists(original_path):
        os.rename(original_path, output_path)
    return output_path

def download_from_drive(link, save_folder, gdrive):
    # You should replace this with your real Google Drive handler logic
    downloaded_files = gdrive.download_files([link], save_folder)
    return downloaded_files

def process_folder(folder, drive_link, gdrive, premiere):
    # Download video file from Google Drive
    messagebox.showinfo("Download", f"Downloading video from Google Drive...")
    downloaded_files = download_from_drive(drive_link, folder, gdrive)
    if not downloaded_files:
        messagebox.showerror("Error", "Failed to download video file.")
        return

    for fname in downloaded_files:
        wait_for_download(fname, folder)
        tape_type = detect_tape_type(fname)
        video_path = os.path.join(folder, fname)
        output_folder = os.path.join(folder, PROCESSED_FOLDER_NAME)
        processed_path = process_video(video_path, tape_type, output_folder, premiere)
        if processed_path:
            final_path = export_video(processed_path, output_folder)
            print(f"Saved processed video: {final_path}")
        else:
            print(f"Processing failed for {fname}")
    messagebox.showinfo("Done", "All videos processed!")

def main_ui():
    root = tk.Tk()
    root.title("Tape-to-Digital Automation")
    root.geometry("450x250")

    # Load configuration
    with open('config/app_settings.json', 'r') as f:
        config = json.load(f)
    
    gdrive = GDriveHandler(config['gdrive'])
    premiere = PremiereAutomation({})
    
    folder_var = tk.StringVar()
    link_var = tk.StringVar()

    def select_folder():
        folder = filedialog.askdirectory(title="Select Customer Folder")
        folder_var.set(folder)

    def start_process():
        folder = folder_var.get()
        link = link_var.get()
        if not folder or not link:
            messagebox.showerror("Missing Info", "Please select a folder and paste a Google Drive link.")
            return
        process_folder(folder, link, gdrive, premiere)

    tk.Label(root, text="Tape-to-Digital Video Editor", font=("Arial", 16)).pack(pady=10)
    tk.Button(root, text="Select Customer Folder", command=select_folder, font=("Arial", 12)).pack()
    tk.Entry(root, textvariable=folder_var, font=("Arial", 12), width=40).pack(pady=5)
    tk.Label(root, text="Paste Google Drive Video Link:", font=("Arial", 12)).pack(pady=(15,2))
    tk.Entry(root, textvariable=link_var, font=("Arial", 12), width=40).pack(pady=5)
    tk.Button(root, text="Start Processing", command=start_process, font=("Arial", 13)).pack(pady=15)

    root.mainloop()

if __name__ == "__main__":
    main_ui()