#!/usr/bin/env python3
"""
ATQ Ventures COM GUI Launcher
Choose between basic and advanced order form interfaces
"""

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import sys
import os

class GUILauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("ATQ Ventures COM - GUI Launcher")
        self.root.geometry("400x300")
        self.root.resizable(False, False)
        
        # Center the window
        self.center_window()
        
        # Create main frame
        main_frame = ttk.Frame(root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(main_frame, text="ATQ Ventures COM", 
                               font=("Arial", 18, "bold"))
        title_label.pack(pady=(0, 20))
        
        subtitle_label = ttk.Label(main_frame, text="Choose your GUI interface", 
                                  font=("Arial", 12))
        subtitle_label.pack(pady=(0, 30))
        
        # Basic GUI button
        basic_button = ttk.Button(main_frame, text="Basic Order Form", 
                                 command=self.launch_basic_gui, width=25)
        basic_button.pack(pady=10)
        
        # Advanced GUI button
        advanced_button = ttk.Button(main_frame, text="Advanced Order Form", 
                                    command=self.launch_advanced_gui, width=25)
        advanced_button.pack(pady=10)
        
        # Exit button
        exit_button = ttk.Button(main_frame, text="Exit", 
                                command=self.root.quit, width=25)
        exit_button.pack(pady=20)
        
        # Version info
        version_label = ttk.Label(main_frame, text="v1.0.0", 
                                 font=("Arial", 8), foreground="gray")
        version_label.pack(side=tk.BOTTOM, pady=10)
        
    def center_window(self):
        """Center the window on screen"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
    
    def launch_basic_gui(self):
        """Launch the basic order form GUI"""
        try:
            if os.path.exists("order_gui.py"):
                subprocess.Popen([sys.executable, "order_gui.py"])
                self.root.withdraw()  # Hide launcher
            else:
                messagebox.showerror("Error", "Basic GUI file (order_gui.py) not found!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch basic GUI: {str(e)}")
    
    def launch_advanced_gui(self):
        """Launch the advanced order form GUI"""
        try:
            if os.path.exists("advanced_order_gui.py"):
                subprocess.Popen([sys.executable, "advanced_order_gui.py"])
                self.root.withdraw()  # Hide launcher
            else:
                messagebox.showerror("Error", "Advanced GUI file (advanced_order_gui.py) not found!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch advanced GUI: {str(e)}")

def main():
    root = tk.Tk()
    app = GUILauncher(root)
    root.mainloop()

if __name__ == "__main__":
    main()
