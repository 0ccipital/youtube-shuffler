#!/usr/bin/env python3
"""
YouTube Channel Shuffler GUI
All data stored locally in ./cache and ./config
"""

import os
import sys
import time
import random
import socket
import subprocess
import json
import time
import hashlib
import platform
import shutil
import traceback
import threading
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# Local directories
CACHE_DIR = Path("./cache")
CONFIG_DIR = Path("./config")
LOG_DIR = Path("./logs")
SOCKET_PATH = "/tmp/mpv-shuffle-socket"
STATE_FILE = CONFIG_DIR / "shuffle_state.json"
LOG_FILE = LOG_DIR / "shuffler.log"
MAX_LOG_SIZE = 5 * 1024 * 1024  # 5MB

# Dark theme colors (macOS inspired)
COLORS = {
    'bg': '#1e1e1e',
    'bg_light': '#2d2d2d',
    'bg_lighter': '#3a3a3a',
    'accent': '#0a84ff',
    'accent_dim': '#0066cc',
    'text': '#ffffff',
    'text_dim': '#98989d',
    'text_dimmer': '#6e6e73',
    'success': '#30d158',
    'error': '#ff453a',
    'warning': '#ff9f0a',
    'border': '#48484a',
}

class LogManager:
    """Manage logging to both GUI and disk with rotation."""
    
    def __init__(self):
        self.log_file = LOG_FILE
        self.max_size = MAX_LOG_SIZE
        self.gui_callback = None
        
        # Ensure log directory exists
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"Warning: Could not create log directory: {e}")
    
    def set_gui_callback(self, callback):
        """Set callback for GUI logging."""
        self.gui_callback = callback
    
    def rotate_if_needed(self):
        """Rotate log file if it exceeds max size."""
        try:
            if self.log_file.exists() and self.log_file.stat().st_size > self.max_size:
                # Keep last 5 rotated logs
                for i in range(4, 0, -1):
                    old_file = LOG_DIR / f"shuffler.log.{i}"
                    new_file = LOG_DIR / f"shuffler.log.{i+1}"
                    if old_file.exists():
                        old_file.rename(new_file)
                
                # Rotate current log to .1
                self.log_file.rename(LOG_DIR / "shuffler.log.1")
        except Exception as e:
            print(f"Warning: Could not rotate log: {e}")
    
    def log(self, message, level="INFO"):
        """Log message to both file and GUI."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{level}] {message}"
        
        # Log to file
        try:
            self.rotate_if_needed()
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_line + "\n")
        except Exception as e:
            print(f"Warning: Could not write to log file: {e}")
        
        # Log to GUI
        if self.gui_callback:
            try:
                # Strip timestamp for GUI (it adds its own)
                gui_message = f"[{level}] {message}" if level != "INFO" else message
                self.gui_callback(gui_message)
            except Exception as e:
                print(f"Warning: Could not write to GUI log: {e}")
    
    def error(self, message, exception=None):
        """Log error with optional exception."""
        if exception:
            tb = traceback.format_exc()
            self.log(f"{message}\n{tb}", "ERROR")
        else:
            self.log(message, "ERROR")
    
    def warning(self, message):
        """Log warning."""
        self.log(message, "WARNING")
    
    def info(self, message):
        """Log info."""
        self.log(message, "INFO")

class DependencyChecker:
    """Check and manage dependencies."""
    
    def __init__(self, logger):
        self.logger = logger
        self.os_type = platform.system()
        self.machine = platform.machine()
        self.is_macos = self.os_type == "Darwin"
        self.is_linux = self.os_type == "Linux"
        self.is_windows = self.os_type == "Windows"
        
    def check_command(self, command):
        """Check if a command is available."""
        try:
            return shutil.which(command) is not None
        except Exception as e:
            self.logger.error(f"Error checking command {command}", e)
            return False
    
    def get_version(self, command, args=['--version']):
        """Get version of a command."""
        try:
            result = subprocess.run(
                [command] + args,
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.strip().split('\n')[0] if result.returncode == 0 else None
        except Exception as e:
            self.logger.warning(f"Could not get version for {command}: {e}")
            return None
    
    def check_dependencies(self):
        """Check all required dependencies."""
        deps = {
            'yt-dlp': self.check_command('yt-dlp'),
            'mpv': self.check_command('mpv'),
        }
        
        versions = {}
        if deps['yt-dlp']:
            versions['yt-dlp'] = self.get_version('yt-dlp')
        if deps['mpv']:
            versions['mpv'] = self.get_version('mpv')
        
        return deps, versions
    
    def get_install_instructions(self):
        """Get platform-specific install instructions."""
        instructions = {
            'title': f'Dependencies Missing ({self.os_type} {self.machine})',
            'brew': None,
            'commands': []
        }
        
        if self.is_macos:
            has_brew = self.check_command('brew')
            instructions['brew'] = has_brew
            
            if has_brew:
                instructions['commands'] = [
                    ('Install yt-dlp', 'brew install yt-dlp'),
                    ('Install mpv', 'brew install mpv'),
                    ('Or visit:', 'https://github.com/yt-dlp/yt-dlp'),
                    ('MPV info:', 'https://github.com/mpv-player/mpv'),
                ]
            else:
                instructions['commands'] = [
                    ('Install Homebrew first', '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'),
                    ('Then install yt-dlp', 'brew install yt-dlp'),
                    ('Then install mpv', 'brew install mpv'),
                    ('Or visit:', 'https://github.com/yt-dlp/yt-dlp'),
                    ('MPV info:', 'https://github.com/mpv-player/mpv'),
                ]
        
        elif self.is_linux:
            if self.check_command('apt'):
                instructions['commands'] = [
                    ('Update package list', 'sudo apt update'),
                    ('Install mpv', 'sudo apt install mpv'),
                    ('Install yt-dlp', 'sudo apt install yt-dlp'),
                    ('Or visit:', 'https://github.com/yt-dlp/yt-dlp'),
                ]
            elif self.check_command('dnf'):
                instructions['commands'] = [
                    ('Install mpv', 'sudo dnf install mpv'),
                    ('For yt-dlp visit:', 'https://github.com/yt-dlp/yt-dlp'),
                ]
            elif self.check_command('pacman'):
                instructions['commands'] = [
                    ('Install mpv', 'sudo pacman -S mpv'),
                    ('Install yt-dlp', 'sudo pacman -S yt-dlp'),
                ]
            else:
                instructions['commands'] = [
                    ('yt-dlp info:', 'https://github.com/yt-dlp/yt-dlp'),
                    ('MPV info:', 'https://github.com/mpv-player/mpv'),
                ]
        
        elif self.is_windows:
            if self.check_command('winget'):
                instructions['commands'] = [
                    ('Install mpv', 'winget install mpv'),
                    ('Install yt-dlp', 'winget install yt-dlp'),
                ]
            elif self.check_command('choco'):
                instructions['commands'] = [
                    ('Install mpv', 'choco install mpv'),
                    ('Install yt-dlp', 'choco install yt-dlp'),
                ]
            else:
                instructions['commands'] = [
                    ('yt-dlp info:', 'https://github.com/yt-dlp/yt-dlp'),
                    ('MPV info:', 'https://github.com/mpv-player/mpv'),
                ]
        
        return instructions
    
    def update_ytdlp(self, log_callback=None):
        """Update yt-dlp."""
        def log(msg):
            if log_callback:
                log_callback(msg)
            self.logger.info(msg)
        
        try:
            log("Updating yt-dlp...")
            
            # Try homebrew first on macOS
            if self.is_macos and self.check_command('brew'):
                log("Attempting update via Homebrew...")
                result = subprocess.run(
                    ['brew', 'upgrade', 'yt-dlp'],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                if result.returncode == 0 or 'already installed' in result.stdout.lower():
                    log("✓ yt-dlp is up to date")
                    return True
                else:
                    log(f"Homebrew upgrade note: {result.stderr[:200]}")
            
            # Try self-update if available
            if self.check_command('yt-dlp'):
                log("Attempting self-update...")
                result = subprocess.run(
                    ['yt-dlp', '-U'],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                if result.returncode == 0:
                    log("✓ yt-dlp updated successfully")
                    return True
            
            # If we get here, provide manual instructions
            log("⚠️  Automatic update not available")
            log("Please update manually:")
            if self.is_macos:
                log("  brew upgrade yt-dlp")
            log("Or visit: https://github.com/yt-dlp/yt-dlp")
            return False
                
        except subprocess.TimeoutExpired:
            log("✗ Update timed out")
            return False
        except Exception as e:
            self.logger.error(f"Error updating yt-dlp", e)
            log(f"✗ Error: {e}")
            log("Visit: https://github.com/yt-dlp/yt-dlp for manual installation")
            return False
    
    def update_mpv(self, log_callback=None):
        """Update mpv."""
        def log(msg):
            if log_callback:
                log_callback(msg)
            self.logger.info(msg)
        
        try:
            log("Updating mpv...")
            
            if self.is_macos and self.check_command('brew'):
                result = subprocess.run(
                    ['brew', 'upgrade', 'mpv'],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                if result.returncode == 0 or 'already installed' in result.stdout.lower():
                    log("✓ mpv is up to date")
                    return True
                else:
                    log(f"Note: {result.stderr[:200]}")
            
            elif self.is_windows and self.check_command('winget'):
                result = subprocess.run(
                    ['winget', 'upgrade', 'mpv'],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                if result.returncode == 0:
                    log("✓ mpv updated successfully")
                    return True
            
            log("⚠️  Please update mpv using your package manager")
            log("Visit: https://github.com/mpv-player/mpv")
            return False
                
        except subprocess.TimeoutExpired:
            log("✗ Update timed out")
            return False
        except Exception as e:
            self.logger.error(f"Error updating mpv", e)
            log(f"✗ Error: {e}")
            log("Visit: https://github.com/mpv-player/mpv for manual installation")
            return False


class YouTubeShuffler:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Shuffler")
        self.root.geometry("600x520")
        self.root.configure(bg=COLORS['bg'])
        
        # Set window icon and title
        try:
            # Set the window title with emoji
            self.root.title("🔀 YouTube Shuffler")
        except:
            self.root.title("YouTube Shuffler")
        
        # Bring window to front on macOS
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after_idle(self.root.attributes, '-topmost', False)
        self.root.focus_force()
        
        # Initialize logger first
        self.logger = LogManager()
        
        self.videos = []
        self.playlist_history = []
        self.current_position = -1
        self.current_channel_url = ""
        self.channel_states = {}
        
        # Collapse states
        self.channel_section_visible = True
        self.log_visible = False
        
        # Dependency checker
        self.dep_checker = DependencyChecker(self.logger)
        
        # Create directories
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            LOG_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Error", f"Could not create directories: {e}")
            self.logger.error("Could not create directories", e)
        
        self.setup_ui()
        
        # Connect logger to GUI
        self.logger.set_gui_callback(self.log)
        
        # Load state after UI is ready
        try:
            self.channel_states = self.load_states()
            self.load_channel_list()
        except Exception as e:
            self.logger.error("Error loading states", e)
            self.channel_states = {}
        
        self.check_mpv_status()
        
        # Check dependencies on startup
        self.root.after(500, self.check_dependencies)
        
        # Set up error handler for uncaught exceptions
        self.root.report_callback_exception = self.handle_exception
        
    def handle_exception(self, exc_type, exc_value, exc_traceback):
        """Handle uncaught exceptions."""
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        self.logger.error(f"Uncaught exception: {error_msg}")
        
        messagebox.showerror(
            "Unexpected Error",
            f"An unexpected error occurred:\n\n{exc_value}\n\nCheck the log for details."
        )
        
    def setup_ui(self):
        # Main container
        main = tk.Frame(self.root, bg=COLORS['bg'])
        main.pack(fill="both", expand=True, padx=0, pady=0)
        
        # ==================== TOP BAR ====================
        topbar = tk.Frame(main, bg=COLORS['bg_light'], height=36)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)
        
        # MPV status (left)
        self.mpv_status = tk.Label(topbar,
                                   text="● MPV",
                                   bg=COLORS['bg_light'],
                                   fg=COLORS['error'],
                                   font=('SF Pro', 11))
        self.mpv_status.pack(side="left", padx=12)
        
        # Channel name (center)
        self.status_label = tk.Label(topbar,
                                     text="No channel loaded",
                                     bg=COLORS['bg_light'],
                                     fg=COLORS['text_dim'],
                                     font=('SF Pro', 11))
        self.status_label.pack(side="left", expand=True)
        
        # Toggle buttons (right) - using consistent size
        btn_frame = tk.Frame(topbar, bg=COLORS['bg_light'])
        btn_frame.pack(side="right", padx=8)
        
        # Use same font size for all icons
        icon_font = ('Arial', 16)
        
        self.deps_btn = tk.Label(btn_frame,
                                 text="🔧",
                                 bg=COLORS['bg_light'],
                                 fg=COLORS['text_dim'],
                                 font=icon_font,
                                 cursor='hand2')
        self.deps_btn.pack(side="left", padx=4)
        self.deps_btn.bind('<Button-1>', lambda e: self.show_dependencies_dialog())
        
        self.toggle_channel_btn = tk.Label(btn_frame,
                                           text="⚙",
                                           bg=COLORS['bg_light'],
                                           fg=COLORS['text_dim'],
                                           font=icon_font,
                                           cursor='hand2')
        self.toggle_channel_btn.pack(side="left", padx=4)
        self.toggle_channel_btn.bind('<Button-1>', lambda e: self.toggle_channel_section())
        
        self.toggle_log_btn = tk.Label(btn_frame,
                                      text="📋",
                                      bg=COLORS['bg_light'],
                                      fg=COLORS['text_dim'],
                                      font=icon_font,
                                      cursor='hand2')
        self.toggle_log_btn.pack(side="left", padx=4)
        self.toggle_log_btn.bind('<Button-1>', lambda e: self.toggle_log())
        
        # ==================== CHANNEL SECTION (Collapsible) ====================
        self.channel_container = tk.Frame(main, bg=COLORS['bg'])
        self.channel_container.pack(fill="x", padx=12, pady=8)
        
        # URL Entry
        url_frame = tk.Frame(self.channel_container, bg=COLORS['bg'])
        url_frame.pack(fill="x", pady=(0, 6))
        
        self.channel_var = tk.StringVar()
        self.channel_combo = ttk.Combobox(url_frame,
                                         textvariable=self.channel_var,
                                         font=('SF Pro', 11),
                                         height=8)
        self.channel_combo.pack(fill="x")
        self.channel_combo.bind('<Return>', lambda e: self.load_channel())
        
        # Control buttons
        control_frame = tk.Frame(self.channel_container, bg=COLORS['bg'])
        control_frame.pack(fill="x")
        
        self.load_btn = self.create_button(control_frame, "Load", self.load_channel)
        self.load_btn.pack(side="left", padx=(0, 6))
        
        self.update_var = tk.BooleanVar(value=False)
        update_check = tk.Checkbutton(control_frame,
                                     text="Force Update",
                                     variable=self.update_var,
                                     bg=COLORS['bg'],
                                     fg=COLORS['text_dim'],
                                     selectcolor=COLORS['bg_light'],
                                     activebackground=COLORS['bg'],
                                     activeforeground=COLORS['text'],
                                     font=('SF Pro', 10),
                                     borderwidth=0,
                                     highlightthickness=0)
        update_check.pack(side="left", padx=6)
        
        self.shuffle_btn = self.create_button(control_frame, "New Shuffle", self.new_shuffle, state="disabled")
        self.shuffle_btn.pack(side="right")
        
        # ==================== NOW PLAYING ====================
        self.playing_frame = tk.Frame(main, bg=COLORS['bg'])
        self.playing_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        
        # Title
        self.title_label = tk.Label(self.playing_frame,
                                    text="No video selected",
                                    bg=COLORS['bg'],
                                    fg=COLORS['text'],
                                    font=('SF Pro', 16, 'bold'),
                                    wraplength=570,
                                    justify="center",
                                    anchor='center')
        self.title_label.pack(pady=(8, 12))
        
        # Metadata
        meta_frame = tk.Frame(self.playing_frame, bg=COLORS['bg'])
        meta_frame.pack(fill="x", pady=(0, 8))
        
        self.meta_label = tk.Label(meta_frame,
                                   text="",
                                   bg=COLORS['bg'],
                                   fg=COLORS['text_dim'],
                                   font=('SF Pro', 10),
                                   justify="center")
        self.meta_label.pack()
        
        # Position
        self.position_label = tk.Label(self.playing_frame,
                                       text="—",
                                       bg=COLORS['bg'],
                                       fg=COLORS['accent'],
                                       font=('SF Pro Mono', 12))
        self.position_label.pack(pady=8)
        
        # ==================== PLAYBACK CONTROLS ====================
        self.controls_bg = tk.Frame(main, bg=COLORS['bg_light'])
        self.controls_bg.pack(fill="x", pady=(0, 0))
        
        controls = tk.Frame(self.controls_bg, bg=COLORS['bg_light'])
        controls.pack(pady=12)
        
        # Previous button
        self.prev_btn = self.create_control_button(controls, "⏮", self.previous_video, state="disabled")
        self.prev_btn.pack(side="left", padx=4)
        
        # Play button (larger)
        self.play_btn_widget = tk.Label(controls,
                                        text="▶",
                                        bg=COLORS['bg_lighter'],
                                        fg=COLORS['text_dim'],
                                        font=('SF Pro', 28),
                                        width=2,
                                        height=1,
                                        relief='flat',
                                        cursor='hand2')
        self.play_btn_widget.pack(side="left", padx=12)
        self.play_btn_widget.command = self.play_current
        self.play_btn_enabled = False
        
        # Next button
        self.next_btn = self.create_control_button(controls, "⏭", self.next_video, state="disabled")
        self.next_btn.pack(side="left", padx=4)
        
        # Keyboard shortcuts
        self.root.bind('<Left>', lambda e: self.previous_video() if getattr(self.prev_btn, 'enabled', False) else None)
        self.root.bind('<Right>', lambda e: self.next_video() if getattr(self.next_btn, 'enabled', False) else None)
        self.root.bind('<space>', lambda e: self.play_current() if self.play_btn_enabled else None)
        
        # ==================== LOG (Collapsible, hidden by default) ====================
        self.log_container = tk.Frame(main, bg=COLORS['bg'])
        
        self.log_text = scrolledtext.ScrolledText(self.log_container,
                                                  height=8,
                                                  font=('SF Mono', 9),
                                                  bg=COLORS['bg_light'],
                                                  fg=COLORS['text_dim'],
                                                  insertbackground=COLORS['text'],
                                                  relief='flat',
                                                  borderwidth=0,
                                                  highlightthickness=0)
        self.log_text.pack(fill="both", expand=True, padx=12, pady=(8, 8))
        self.log_text.config(state="disabled")
        
        # Configure ttk styles for dark theme
        style = ttk.Style()
        style.theme_use('default')
        
        style.configure('TCombobox',
                       fieldbackground=COLORS['bg_lighter'],
                       background=COLORS['bg_lighter'],
                       foreground=COLORS['text'],
                       borderwidth=0,
                       lightcolor=COLORS['bg_lighter'],
                       darkcolor=COLORS['bg_lighter'])
        
        style.map('TCombobox',
                 fieldbackground=[('readonly', COLORS['bg_lighter'])],
                 selectbackground=[('readonly', COLORS['bg_lighter'])],
                 selectforeground=[('readonly', COLORS['text'])])
    
    def check_dependencies(self):
        """Check dependencies on startup."""
        try:
            deps, versions = self.dep_checker.check_dependencies()
            
            missing = [name for name, installed in deps.items() if not installed]
            
            if missing:
                self.logger.warning(f"Missing dependencies: {', '.join(missing)}")
                self.deps_btn.config(fg=COLORS['warning'])
                
                # Show dialog after a delay if dependencies are missing
                if missing:
                    self.root.after(1000, lambda: self.show_dependencies_dialog(auto_show=True))
            else:
                self.logger.info("All dependencies found")
                for name, version in versions.items():
                    if version:
                        self.logger.info(f"  {name}: {version}")
                self.deps_btn.config(fg=COLORS['success'])
        except Exception as e:
            self.logger.error("Error checking dependencies", e)
            self.deps_btn.config(fg=COLORS['error'])
    
    def show_dependencies_dialog(self, auto_show=False):
        """Show dependencies management dialog."""
        try:
            dialog = tk.Toplevel(self.root)
            dialog.title("Dependencies Manager")
            dialog.geometry("600x500")
            dialog.configure(bg=COLORS['bg'])
            
            # Make it modal
            dialog.transient(self.root)
            dialog.grab_set()
            
            # Header
            header = tk.Frame(dialog, bg=COLORS['bg_light'])
            header.pack(fill="x", padx=0, pady=0)
            
            tk.Label(header,
                    text="🔧 Dependencies Manager",
                    bg=COLORS['bg_light'],
                    fg=COLORS['text'],
                    font=('SF Pro', 14, 'bold')).pack(pady=12, padx=12)
            
            # Content
            content = tk.Frame(dialog, bg=COLORS['bg'])
            content.pack(fill="both", expand=True, padx=20, pady=20)
            
            # Check status
            deps, versions = self.dep_checker.check_dependencies()
            
            # Status section
            status_frame = tk.Frame(content, bg=COLORS['bg'])
            status_frame.pack(fill="x", pady=(0, 15))
            
            tk.Label(status_frame,
                    text="Status:",
                    bg=COLORS['bg'],
                    fg=COLORS['text'],
                    font=('SF Pro', 12, 'bold')).pack(anchor="w", pady=(0, 8))
            
            for name, installed in deps.items():
                item_frame = tk.Frame(status_frame, bg=COLORS['bg'])
                item_frame.pack(fill="x", pady=2)
                
                status_icon = "✓" if installed else "✗"
                status_color = COLORS['success'] if installed else COLORS['error']
                
                tk.Label(item_frame,
                        text=f"{status_icon} {name}",
                        bg=COLORS['bg'],
                        fg=status_color,
                        font=('SF Pro', 11),
                        width=15,
                        anchor='w').pack(side="left")
                
                if installed and name in versions:
                    tk.Label(item_frame,
                            text=versions[name],
                            bg=COLORS['bg'],
                            fg=COLORS['text_dim'],
                            font=('SF Mono', 9)).pack(side="left")
            
            # Actions section
            actions_frame = tk.Frame(content, bg=COLORS['bg'])
            actions_frame.pack(fill="x", pady=(15, 0))
            
            tk.Label(actions_frame,
                    text="Actions:",
                    bg=COLORS['bg'],
                    fg=COLORS['text'],
                    font=('SF Pro', 12, 'bold')).pack(anchor="w", pady=(0, 8))
            
            # Update buttons - using Labels styled as buttons
            btn_frame = tk.Frame(actions_frame, bg=COLORS['bg'])
            btn_frame.pack(fill="x", pady=5)
            
            def update_ytdlp():
                btn_update_ytdlp.config(bg=COLORS['bg_light'])
                dialog_log.insert('end', "\n")
                try:
                    success = self.dep_checker.update_ytdlp(
                        lambda msg: dialog_log.insert('end', msg + '\n')
                    )
                    dialog_log.see('end')
                    if success:
                        self.root.after(500, self.check_dependencies)
                except Exception as e:
                    self.logger.error("Error updating yt-dlp", e)
                    dialog_log.insert('end', f"Error: {e}\n")
                finally:
                    btn_update_ytdlp.config(bg=COLORS['bg_lighter'])
            
            def update_mpv():
                btn_update_mpv.config(bg=COLORS['bg_light'])
                dialog_log.insert('end', "\n")
                try:
                    success = self.dep_checker.update_mpv(
                        lambda msg: dialog_log.insert('end', msg + '\n')
                    )
                    dialog_log.see('end')
                    if success:
                        self.root.after(500, self.check_dependencies)
                except Exception as e:
                    self.logger.error("Error updating mpv", e)
                    dialog_log.insert('end', f"Error: {e}\n")
                finally:
                    btn_update_mpv.config(bg=COLORS['bg_lighter'])
            
            # Create button-styled labels
            btn_update_ytdlp = tk.Label(btn_frame,
                                        text="Update yt-dlp",
                                        bg=COLORS['bg_lighter'],
                                        fg=COLORS['text'],
                                        font=('SF Pro', 10),
                                        padx=12,
                                        pady=6,
                                        relief='flat',
                                        cursor='hand2')
            btn_update_ytdlp.pack(side="left", padx=(0, 8))
            btn_update_ytdlp.bind('<Button-1>', lambda e: update_ytdlp())
            btn_update_ytdlp.bind('<Enter>', lambda e: btn_update_ytdlp.config(bg=COLORS['accent_dim']))
            btn_update_ytdlp.bind('<Leave>', lambda e: btn_update_ytdlp.config(bg=COLORS['bg_lighter']))
            
            btn_update_mpv = tk.Label(btn_frame,
                                      text="Update mpv",
                                      bg=COLORS['bg_lighter'],
                                      fg=COLORS['text'],
                                      font=('SF Pro', 10),
                                      padx=12,
                                      pady=6,
                                      relief='flat',
                                      cursor='hand2')
            btn_update_mpv.pack(side="left")
            btn_update_mpv.bind('<Button-1>', lambda e: update_mpv())
            btn_update_mpv.bind('<Enter>', lambda e: btn_update_mpv.config(bg=COLORS['accent_dim']))
            btn_update_mpv.bind('<Leave>', lambda e: btn_update_mpv.config(bg=COLORS['bg_lighter']))
            
            # Install instructions
            if any(not installed for installed in deps.values()):
                instructions = self.dep_checker.get_install_instructions()
                
                inst_frame = tk.Frame(content, bg=COLORS['bg'])
                inst_frame.pack(fill="both", expand=True, pady=(15, 0))
                
                tk.Label(inst_frame,
                        text="Installation Instructions:",
                        bg=COLORS['bg'],
                        fg=COLORS['text'],
                        font=('SF Pro', 12, 'bold')).pack(anchor="w", pady=(0, 8))
                
                inst_text = scrolledtext.ScrolledText(inst_frame,
                                                     height=8,
                                                     bg=COLORS['bg_light'],
                                                     fg=COLORS['text_dim'],
                                                     font=('SF Mono', 9),
                                                     relief='flat',
                                                     borderwidth=0)
                inst_text.pack(fill="both", expand=True)
                
                for desc, cmd in instructions['commands']:
                    inst_text.insert('end', f"{desc}:\n", 'bold')
                    inst_text.insert('end', f"  {cmd}\n\n")
                
                inst_text.tag_config('bold', foreground=COLORS['text'], font=('SF Mono', 9, 'bold'))
                inst_text.config(state='disabled')
            
            # Log output
            log_frame = tk.Frame(content, bg=COLORS['bg'])
            log_frame.pack(fill="both", expand=True, pady=(15, 0))
            
            tk.Label(log_frame,
                    text="Output:",
                    bg=COLORS['bg'],
                    fg=COLORS['text'],
                    font=('SF Pro', 12, 'bold')).pack(anchor="w", pady=(0, 8))
            
            dialog_log = scrolledtext.ScrolledText(log_frame,
                                                  height=6,
                                                  bg=COLORS['bg_light'],
                                                  fg=COLORS['text_dim'],
                                                  font=('SF Mono', 9),
                                                  relief='flat',
                                                  borderwidth=0)
            dialog_log.pack(fill="both", expand=True)
            
            # Close button - using Label styled as button
            close_btn = tk.Label(dialog,
                                text="Close",
                                bg=COLORS['accent'],
                                fg=COLORS['text'],
                                font=('SF Pro', 11),
                                padx=20,
                                pady=8,
                                relief='flat',
                                cursor='hand2')
            close_btn.pack(pady=15)
            close_btn.bind('<Button-1>', lambda e: dialog.destroy())
            close_btn.bind('<Enter>', lambda e: close_btn.config(bg=COLORS['accent_dim']))
            close_btn.bind('<Leave>', lambda e: close_btn.config(bg=COLORS['accent']))
            
        except Exception as e:
            self.logger.error("Error showing dependencies dialog", e)
            messagebox.showerror("Error", f"Could not show dependencies dialog: {e}")
    
    def create_button(self, parent, text, command, state="normal"):
        """Create a styled button."""
        btn = tk.Label(parent,
                      text=text,
                      bg=COLORS['bg_lighter'] if state == "normal" else COLORS['bg_light'],
                      fg=COLORS['text'] if state == "normal" else COLORS['text_dimmer'],
                      font=('SF Pro', 10),
                      padx=12,
                      pady=4,
                      relief='flat',
                      cursor='hand2' if state == "normal" else 'arrow')
        
        btn.command = command
        btn.enabled = (state == "normal")
        
        if state == "normal":
            btn.bind('<Button-1>', lambda e: self.safe_call(btn.command))
            btn.bind('<Enter>', lambda e: btn.config(bg=COLORS['bg_light']))
            btn.bind('<Leave>', lambda e: btn.config(bg=COLORS['bg_lighter']))
        
        return btn
    
    def create_control_button(self, parent, text, command, state="normal"):
        """Create a playback control button."""
        btn = tk.Label(parent,
                      text=text,
                      bg=COLORS['bg_lighter'] if state == "normal" else COLORS['bg_light'],
                      fg=COLORS['text'] if state == "normal" else COLORS['text_dimmer'],
                      font=('SF Pro', 20),
                      width=2,
                      height=1,
                      relief='flat',
                      cursor='hand2' if state == "normal" else 'arrow')
        
        btn.command = command
        btn.enabled = (state == "normal")
        
        if state == "normal":
            btn.bind('<Button-1>', lambda e: self.safe_call(btn.command))
            btn.bind('<Enter>', lambda e: btn.config(bg=COLORS['accent_dim']))
            btn.bind('<Leave>', lambda e: btn.config(bg=COLORS['bg_lighter']))
        
        return btn
    
    def safe_call(self, func):
        """Safely call a function with error handling."""
        try:
            func()
        except Exception as e:
            self.logger.error(f"Error in {func.__name__}", e)
            messagebox.showerror("Error", f"An error occurred: {e}")
    
    def update_button_state(self, btn, enabled):
        """Update button enabled/disabled state."""
        try:
            btn.enabled = enabled
            if enabled:
                btn.config(bg=COLORS['bg_lighter'], fg=COLORS['text'], cursor='hand2')
                btn.bind('<Button-1>', lambda e: self.safe_call(btn.command))
                btn.bind('<Enter>', lambda e: btn.config(bg=COLORS['bg_light']))
                btn.bind('<Leave>', lambda e: btn.config(bg=COLORS['bg_lighter']))
            else:
                btn.config(bg=COLORS['bg_light'], fg=COLORS['text_dimmer'], cursor='arrow')
                btn.unbind('<Button-1>')
                btn.unbind('<Enter>')
                btn.unbind('<Leave>')
        except Exception as e:
            self.logger.error("Error updating button state", e)
    
    def update_control_button(self, btn, enabled):
        """Update control button state."""
        try:
            btn.enabled = enabled
            if enabled:
                btn.config(bg=COLORS['bg_lighter'], fg=COLORS['text'], cursor='hand2')
                btn.bind('<Button-1>', lambda e: self.safe_call(btn.command))
                btn.bind('<Enter>', lambda e: btn.config(bg=COLORS['accent_dim']))
                btn.bind('<Leave>', lambda e: btn.config(bg=COLORS['bg_lighter']))
            else:
                btn.config(bg=COLORS['bg_light'], fg=COLORS['text_dimmer'], cursor='arrow')
                btn.unbind('<Button-1>')
                btn.unbind('<Enter>')
                btn.unbind('<Leave>')
        except Exception as e:
            self.logger.error("Error updating control button state", e)
    
    def update_play_button(self, enabled):
        """Update play button state."""
        try:
            self.play_btn_enabled = enabled
            if enabled:
                self.play_btn_widget.config(fg=COLORS['text'], cursor='hand2')
                self.play_btn_widget.bind('<Button-1>', lambda e: self.safe_call(self.play_btn_widget.command))
                self.play_btn_widget.bind('<Enter>', lambda e: self.play_btn_widget.config(bg=COLORS['accent_dim']))
                self.play_btn_widget.bind('<Leave>', lambda e: self.play_btn_widget.config(bg=COLORS['bg_lighter']))
            else:
                self.play_btn_widget.config(fg=COLORS['text_dimmer'], cursor='arrow')
                self.play_btn_widget.unbind('<Button-1>')
                self.play_btn_widget.unbind('<Enter>')
                self.play_btn_widget.unbind('<Leave>')
        except Exception as e:
            self.logger.error("Error updating play button state", e)
    
    def toggle_channel_section(self):
        """Toggle channel section visibility."""
        try:
            if self.channel_section_visible:
                self.channel_container.pack_forget()
                new_height = 400 if not self.log_visible else 600
                self.root.geometry(f"600x{new_height}")
            else:
                self.channel_container.pack(after=self.root.winfo_children()[0].winfo_children()[0], fill="x", padx=12, pady=8)
                new_height = 520 if not self.log_visible else 720
                self.root.geometry(f"600x{new_height}")
            self.channel_section_visible = not self.channel_section_visible
        except Exception as e:
            self.logger.error("Error toggling channel section", e)
    
    def toggle_log(self):
        """Toggle log visibility."""
        try:
            if self.log_visible:
                self.log_container.pack_forget()
                new_height = 520 if self.channel_section_visible else 400
                self.root.geometry(f"600x{new_height}")
                self.log_visible = False
            else:
                self.log_container.pack(before=self.controls_bg, fill="x", padx=0, pady=0)
                new_height = 720 if self.channel_section_visible else 600
                self.root.geometry(f"600x{new_height}")
                self.log_visible = True
        except Exception as e:
            self.logger.error("Error toggling log", e)
    
    def log(self, message):
        """Add message to log window."""
        try:
            self.log_text.config(state="normal")
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert("end", f"[{timestamp}] {message}\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        except Exception as e:
            print(f"Error writing to log: {e}")
        
    def check_mpv_status(self):
        """Periodically check if MPV is running."""
        try:
            if self.mpv_running():
                self.mpv_status.config(text="● MPV", fg=COLORS['success'])
            else:
                self.mpv_status.config(text="● MPV", fg=COLORS['error'])
        except Exception as e:
            self.logger.error("Error checking MPV status", e)
        finally:
            self.root.after(2000, self.check_mpv_status)
        
    def load_channel_list(self):
        """Load list of previously used channels."""
        try:
            channels = list(self.channel_states.keys())
            if channels:
                self.channel_combo['values'] = channels
                # Don't auto-select - let it be blank or show current
                # Only set if we don't have a current channel
                if not self.current_channel_url and not self.channel_var.get():
                    self.channel_combo.current(0)
        except Exception as e:
            self.logger.error("Error loading channel list", e)
    
    def update_channel_dropdown(self, channel_url):
        """Update dropdown to show the current channel."""
        try:
            # Get current channels and add new one if needed
            channels = list(self.channel_states.keys())
            
            # Ensure current channel is in the list
            if channel_url not in channels:
                channels.append(channel_url)
            
            # Update dropdown values
            self.channel_combo['values'] = channels
            
            # Set the current channel as selected
            if channel_url in channels:
                index = channels.index(channel_url)
                self.channel_combo.current(index)
            else:
                # Fallback: set directly
                self.channel_var.set(channel_url)
                
            self.logger.info(f"Dropdown updated to show: {channel_url[:50]}...")
                
        except Exception as e:
            self.logger.error("Error updating channel dropdown", e)
            
    def get_cache_path(self, channel_url):
        """Generate a cache filename based on channel URL."""
        try:
            url_hash = hashlib.md5(channel_url.encode()).hexdigest()[:12]
            return CACHE_DIR / f"channel_{url_hash}.json"
        except Exception as e:
            self.logger.error("Error generating cache path", e)
            raise
    
    def normalize_channel_url(self, url):
        """Ensure we're pointing to the /videos tab of the channel."""
        try:
            if not url:
                raise ValueError("Empty URL")
            
            url = url.strip().rstrip('/')
            
            # Basic URL validation
            if not url.startswith(('http://', 'https://')):
                raise ValueError("URL must start with http:// or https://")
            
            if 'youtube.com' not in url and 'youtu.be' not in url:
                raise ValueError("URL must be a YouTube URL")
            
            if '/@' in url or '/c/' in url or '/user/' in url or '/channel/' in url:
                if not url.endswith('/videos'):
                    url = url + '/videos'
            
            return url
        except Exception as e:
            self.logger.error(f"Error normalizing URL: {url}", e)
            raise
    
    def fetch_video_metadata(self, video_url):
        """Fetch full metadata for a single video (background task)."""
        try:
            result = subprocess.run(
                [
                    "yt-dlp",
                    "--dump-single-json",
                    "--no-warnings",
                    video_url
                ],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                return {
                    "upload_date": data.get("upload_date", ""),
                    "view_count": data.get("view_count", 0),
                    "duration": data.get("duration", 0),
                    "channel": data.get("channel", data.get("uploader", "Unknown")),
                    "title": data.get("title", "Unknown"),
                }
        except subprocess.TimeoutExpired:
            self.logger.warning("Metadata fetch timed out")
        except Exception as e:
            self.logger.warning(f"Could not fetch metadata: {e}")
        return None
    
    def update_video_metadata_async(self, video_index):
        """Fetch and update full metadata for a video (runs in background thread)."""
        def fetch_and_update():
            try:
                if video_index >= len(self.videos):
                    return
                
                video = self.videos[video_index]
                
                # Only fetch if we don't have a valid upload date
                #if video.get("upload_date") and len(video.get("upload_date", "")) == 8:
                #    return  # Already have good metadata
                
                self.logger.info("Fetching full metadata in 2 sec...")
                time.sleep(2)
                
                # Fetch full metadata
                metadata = self.fetch_video_metadata(video["url"])
                
                if metadata:
                    # Update the video in our list
                    self.videos[video_index].update(metadata)
                    
                    # Update the display if this is still the current video (use after to be thread-safe)
                    if self.current_position == video_index:
                        self.root.after(0, self.show_current_video)
                        self.logger.info("✓ Updated with full metadata")
                    
                    # Update cache with new metadata
                    if self.current_channel_url:
                        cache_file = self.get_cache_path(self.current_channel_url)
                        try:
                            with open(cache_file, "w", encoding="utf-8") as f:
                                json.dump(self.videos, f, indent=2)
                        except Exception as e:
                            self.logger.warning(f"Could not update cache: {e}")
                            
            except Exception as e:
                self.logger.error("Error updating video metadata", e)
        
        # Run in background thread so UI doesn't freeze
        thread = threading.Thread(target=fetch_and_update, daemon=True)
        thread.start()
    
    def fetch_channel_videos(self, channel_url, force_refresh=False):
        """Fetch all videos from a YouTube channel using yt-dlp (fast flat-playlist)."""
        try:
            # Validate yt-dlp is available
            if not self.dep_checker.check_command('yt-dlp'):
                raise RuntimeError("yt-dlp is not installed. Please install it from the Dependencies Manager.")
            
            cache_file = self.get_cache_path(channel_url)
            
            if cache_file.exists() and not force_refresh:
                self.logger.info("Loading from cache")
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if not data or not isinstance(data, list):
                            raise ValueError("Invalid cache data")
                        self.logger.info(f"Found {len(data)} videos")
                        return data
                except json.JSONDecodeError as e:
                    self.logger.warning(f"Cache file corrupted, re-fetching: {e}")
                    cache_file.unlink()  # Delete corrupted cache
            
            channel_url = self.normalize_channel_url(channel_url)
            self.logger.info(f"Fetching videos from {channel_url}")
            self.root.update()
            
            # Use --dump-single-json for faster fetching (metadata fetched per-video on play)
            result = subprocess.run(
                [
                    "yt-dlp",
                    "--flat-playlist",
                    "--dump-single-json",
                    "--no-warnings",
                    channel_url
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=120
            )
            
            if not result.stdout:
                raise ValueError("No data returned from yt-dlp")
            
            data = json.loads(result.stdout)
            
            if not data or "entries" not in data:
                raise ValueError("Invalid response from yt-dlp")
            
            channel_name = (data.get("playlist_channel") or 
                          data.get("playlist_uploader") or 
                          data.get("uploader") or 
                          data.get("channel") or 
                          "Unknown")
            
            videos = []
            
            for entry in data.get("entries", []):
                if not entry or "id" not in entry:
                    continue
                
                if entry["id"].startswith("UC"):
                    continue
                
                try:
                    video = {
                        "url": entry.get("url", f"https://www.youtube.com/watch?v={entry['id']}"),
                        "title": entry.get("title", "Unknown"),
                        "channel": channel_name,
                        "upload_date": entry.get("upload_date", ""),  # May be empty, will fetch on play
                        "view_count": entry.get("view_count", 0) if entry.get("view_count") else 0,
                        "duration": int(entry.get("duration", 0)) if entry.get("duration") else 0,
                    }
                    videos.append(video)
                except Exception as e:
                    self.logger.warning(f"Error processing video entry: {e}")
                    continue
            
            if not videos:
                raise ValueError("No videos found in channel")
            
            # Save to cache
            try:
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(videos, f, indent=2)
            except Exception as e:
                self.logger.warning(f"Could not write cache: {e}")
            
            self.logger.info(f"Cached {len(videos)} videos")
            return videos
            
        except subprocess.TimeoutExpired:
            self.logger.error("Request timed out")
            messagebox.showerror("Error", "Request timed out. The channel might be too large or network is slow.")
            return []
        except subprocess.CalledProcessError as e:
            self.logger.error(f"yt-dlp error: {e.stderr}", e)
            messagebox.showerror("Error", f"Failed to fetch channel.\n\nMake sure the URL is correct and yt-dlp is working.\n\nError: {e.stderr[:200]}")
            return []
        except json.JSONDecodeError as e:
            self.logger.error("Invalid JSON from yt-dlp", e)
            messagebox.showerror("Error", "Received invalid data from yt-dlp. The channel URL might be incorrect.")
            return []
        except ValueError as e:
            self.logger.error(f"Validation error: {e}")
            messagebox.showerror("Error", str(e))
            return []
        except Exception as e:
            self.logger.error("Unexpected error fetching videos", e)
            messagebox.showerror("Error", f"An unexpected error occurred:\n\n{e}")
            return []
    
    def load_channel(self):
        """Load a channel and its videos."""
        try:
            channel_url = self.channel_var.get().strip()
            if not channel_url:
                messagebox.showwarning("Warning", "Please enter a channel URL")
                return
            
            self.update_button_state(self.load_btn, False)
            self.root.update()
            
            force_update = self.update_var.get()
            
            # Check if we're switching to a different channel
            is_switching_channel = (self.current_channel_url and 
                                   self.current_channel_url != channel_url)
            
            # If switching channels, save current channel state first
            if is_switching_channel:
                self.logger.info(f"Switching channels")
                self.logger.info(f"  From: {self.current_channel_url[:50]}...")
                self.logger.info(f"  To: {channel_url[:50]}...")
                self.save_states()  # Save old channel state
            
            # Fetch new channel videos
            videos = self.fetch_channel_videos(channel_url, force_update)
            
            if not videos:
                return
            
            # Update to new channel
            self.videos = videos
            self.current_channel_url = channel_url
            
            # Determine whether to load saved state or start fresh
            should_load_state = (channel_url in self.channel_states and 
                                not force_update and 
                                not is_switching_channel)
            
            if should_load_state:
                # Resume existing channel where we left off
                state = self.channel_states[channel_url]
                self.playlist_history = state.get("history", [])
                self.current_position = state.get("position", -1)
                
                # Validate history indices match current video count
                self.playlist_history = [i for i in self.playlist_history if 0 <= i < len(videos)]
                if self.current_position >= len(self.playlist_history):
                    self.current_position = len(self.playlist_history) - 1
                
                if self.playlist_history:
                    self.logger.info(f"Resuming: {len(self.playlist_history)} videos in history")
            else:
                # Start fresh (new channel, switching, or force update)
                if is_switching_channel:
                    self.logger.info("Starting fresh on new channel")
                elif force_update:
                    self.logger.info("Force update - clearing history")
                else:
                    self.logger.info("New channel - starting fresh")
                    
                self.playlist_history = []
                self.current_position = -1
            
            # Update UI
            channel_name = videos[0].get("channel", "Unknown")
            self.status_label.config(
                text=f"{channel_name} • {len(videos):,} videos", 
                fg=COLORS['text']
            )
            
            # Enable/disable buttons based on state
            self.update_button_state(self.shuffle_btn, True)
            self.update_control_button(self.next_btn, True)
            
            if self.playlist_history and self.current_position >= 0:
                # Has history - enable playback
                self.update_play_button(True)
                self.update_control_button(self.prev_btn, self.current_position > 0)
                self.show_current_video()
                self.logger.info("Ready to resume playback")
            else:
                # No history - disable playback until next is clicked
                self.update_play_button(False)
                self.update_control_button(self.prev_btn, False)
                self.clear_video_info()
                self.logger.info("Click 'Next' to start playing")
            
            # Update dropdown to show current channel
            self.update_channel_dropdown(channel_url)
            
            # Save state for new channel
            self.save_states()
            
        except Exception as e:
            self.logger.error("Error loading channel", e)
            messagebox.showerror("Error", f"Could not load channel:\n\n{e}")
        finally:
            self.update_button_state(self.load_btn, True)
    
    def new_shuffle(self):
        """Start a new shuffle."""
        try:
            if messagebox.askyesno("New Shuffle", "Clear history and start fresh?"):
                self.playlist_history = []
                self.current_position = -1
                self.update_control_button(self.prev_btn, False)
                self.update_play_button(False)
                self.logger.info("New shuffle started")
                self.save_states()
                self.clear_video_info()
        except Exception as e:
            self.logger.error("Error starting new shuffle", e)
    
    def next_video(self):
        """Play next random video."""
        try:
            if not self.videos:
                self.logger.warning("No videos loaded")
                return
            
            if self.current_position < len(self.playlist_history) - 1:
                self.current_position += 1
                self.logger.info("Moving forward in history")
            else:
                new_index = random.randint(0, len(self.videos) - 1)
                if self.current_position < len(self.playlist_history) - 1:
                    self.playlist_history = self.playlist_history[:self.current_position + 1]
                self.playlist_history.append(new_index)
                self.current_position = len(self.playlist_history) - 1
                self.logger.info("Selected random video")
            
            self.show_current_video()
            self.update_control_button(self.prev_btn, True)
            self.update_play_button(True)
            self.root.update_idletasks()
            
            self.play_current()
            self.save_states()
            
        except Exception as e:
            self.logger.error("Error playing next video", e)
            messagebox.showerror("Error", f"Could not play next video:\n\n{e}")
    
    def previous_video(self):
        """Go back to previous video."""
        try:
            if self.current_position > 0:
                self.current_position -= 1
                self.logger.info("Going back in history")
                self.show_current_video()
                
                if self.current_position == 0:
                    self.update_control_button(self.prev_btn, False)
                
                self.root.update_idletasks()
                self.play_current()
                self.save_states()
        except Exception as e:
            self.logger.error("Error playing previous video", e)
            messagebox.showerror("Error", f"Could not play previous video:\n\n{e}")
    
    def show_current_video(self):
        """Display current video information."""
        try:
            if not self.playlist_history or self.current_position < 0:
                return
            
            video_index = self.playlist_history[self.current_position]
            if video_index >= len(self.videos):
                self.logger.error(f"Invalid video index: {video_index}")
                return
                
            video = self.videos[video_index]
            
            title = video.get("title", "Unknown")
            self.title_label.config(text=title)
            self.logger.info(f"Showing: {title[:60]}")
            
            meta_parts = []
            
            # Upload date
            upload_date = video.get("upload_date", "")
            if upload_date and upload_date != "NA" and len(upload_date) == 8:
                try:
                    date_obj = datetime.strptime(upload_date, "%Y%m%d")
                    meta_parts.append(date_obj.strftime("%b %d, %Y"))
                except:
                    pass
            
            # Views
            views = video.get("view_count", 0)
            if views and views > 0:
                meta_parts.append(f"{views:,} views")
            
            # Duration
            duration = video.get("duration", 0)
            if duration and duration > 0:
                hours = duration // 3600
                minutes = (duration % 3600) // 60
                seconds = duration % 60
                if hours > 0:
                    meta_parts.append(f"{hours}:{minutes:02d}:{seconds:02d}")
                else:
                    meta_parts.append(f"{minutes}:{seconds:02d}")
            
            if meta_parts:
                self.meta_label.config(text=" • ".join(meta_parts))
            else:
                self.meta_label.config(text="Loading metadata...")
            
            self.position_label.config(text=f"{self.current_position + 1} / {len(self.playlist_history)}")
            
        except Exception as e:
            self.logger.error("Error showing video info", e)
    
    def clear_video_info(self):
        """Clear all video info displays."""
        try:
            self.title_label.config(text="No video selected")
            self.meta_label.config(text="")
            self.position_label.config(text="—")
        except Exception as e:
            self.logger.error("Error clearing video info", e)
    
    def play_current(self):
        """Play the current video in MPV."""
        try:
            if not self.playlist_history or self.current_position < 0:
                self.logger.warning("No video to play")
                return
            
            if not self.mpv_running():
                self.logger.info("Starting MPV...")
                self.start_mpv_instance()
                time.sleep(0.5)
                if not self.mpv_running():
                    self.logger.error("MPV failed to start")
                    messagebox.showerror("Error", "Could not start MPV.\n\nMake sure MPV is installed correctly.")
                    return
            
            video_index = self.playlist_history[self.current_position]
            if video_index >= len(self.videos):
                self.logger.error("Invalid video index")
                return
                
            video = self.videos[video_index]
            
            # Start playback immediately (no delay)
            self.send_command(["loadfile", video["url"], "replace"])
            self.logger.info(f"Playing: {video.get('title', 'Unknown')[:50]}")
            
            # Fetch full metadata in background while MPV loads
            # This updates the display with complete info including upload date
            self.root.after(100, lambda: self.update_video_metadata_async(video_index))
            
        except Exception as e:
            self.logger.error("Error playing video", e)
            messagebox.showerror("Error", f"Could not play video:\n\n{e}")
    
    def mpv_running(self):
        """Check if mpv IPC socket exists and can be connected."""
        if not os.path.exists(SOCKET_PATH):
            return False
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(0.2)
            sock.connect(SOCKET_PATH)
            sock.close()
            return True
        except (OSError, socket.error):
            return False
    
    def start_mpv_instance(self):
        """Start mpv in detached mode with idle and IPC."""
        try:
            if not self.dep_checker.check_command('mpv'):
                raise RuntimeError("MPV is not installed")
            
            if os.path.exists(SOCKET_PATH):
                os.remove(SOCKET_PATH)

# TODO make into gui for compressing audio

# For “sleep” listening with rowdy gaming channels (yells/laughs peaking way above normal speech), these chains work well:

# Option A: Heavy leveling (2-stage compressor + limiter)

# Smooth general leveling, plus a fast “catch the yells” stage, then a brickwall limiter.
# Good when you want aggressive peak control without totally crushing intelligibility.

# Use this in your start_mpv_instance args:
# "--af=lavfi=[acompressor=threshold=-22dB:ratio=2.5:attack=10:release=350:makeup=4dB:knee=6:detection=rms:link=average],lavfi=[acompressor=threshold=-12dB:ratio=8:attack=2:release=120:makeup=0dB:knee=4:detection=peak:link=maximum],lavfi=[alimiter=limit=0.90:attack=5:release=50]"

# Why these values:

# Stage 1 (RMS detection): gentle leveling with slower release to avoid pumping.
# Stage 2 (PEAK detection): fast clamp for shouts/laughs.
# Limiter: 0.90 ceiling keeps headroom; adjust to 0.94 if it feels too soft.

# Option B: Dynamic normalizer + limiter (rides dialog up, tames peaks)

# If their mic balance varies a lot between speakers, this can be very comfy for sleep.

# "--af=lavfi=[dynaudnorm=f=350:g=10:p=0.45:n=1],lavfi=[alimiter=limit=0.90:attack=5:release=40]"

# Tips:

# f=350 makes it react a bit slower (smoother), g=10 caps max boost so noise doesn’t rise too much, p=0.45 keeps things from getting too loud, n=1 couples channels to avoid stereo wobble.

# Option C: Medium/transparent “always-on” + limiter

# If A feels too squashed, try:

# "--af=lavfi=[acompressor=threshold=-18dB:ratio=2.2:attack=8:release=250:makeup=2dB:knee=6:detection=rms:link=average],lavfi=[alimiter=limit=0.94:attack=5:release=50]"
            subprocess.Popen(
                [
                    "mpv",
                    "--idle=yes",
                    "--force-window=yes",
                    "--af=lavfi=[dynaudnorm=f=350:g=10:p=0.45:n=1],lavfi=[alimiter=limit=0.90:attack=5:release=40]",
                    f"--input-ipc-server={SOCKET_PATH}"
                ],
                preexec_fn=os.setsid,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            
            for _ in range(20):
                if self.mpv_running():
                    self.logger.info("MPV started successfully")
                    return
                time.sleep(0.2)
            
            raise RuntimeError("MPV did not create IPC socket")
            
        except Exception as e:
            self.logger.error("Error starting MPV", e)
            raise
    
    def send_command(self, command):
        """Send JSON command to mpv via IPC socket."""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect(SOCKET_PATH)
            sock.sendall((json.dumps({"command": command}) + "\n").encode("utf-8"))
            sock.close()
        except Exception as e:
            self.logger.error("Error sending command to MPV", e)
            raise
    
    def load_states(self):
        """Load saved channel states."""
        try:
            if STATE_FILE.exists():
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
                    else:
                        self.logger.warning("Invalid state file format")
                        return {}
        except json.JSONDecodeError as e:
            self.logger.error("Corrupted state file", e)
            # Backup corrupted file
            if STATE_FILE.exists():
                backup = STATE_FILE.with_suffix('.json.bak')
                STATE_FILE.rename(backup)
                self.logger.info(f"Backed up corrupted state to {backup}")
            return {}
        except Exception as e:
            self.logger.error("Error loading states", e)
            return {}
        
        return {}
    
    def save_states(self):
        """Save current channel state."""
        try:
            if not self.current_channel_url:
                return
            
            self.channel_states[self.current_channel_url] = {
                "history": self.playlist_history,
                "position": self.current_position,
                "last_used": datetime.now().isoformat()
            }
            
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            
            # Write to temp file first, then rename (atomic operation)
            temp_file = STATE_FILE.with_suffix('.json.tmp')
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.channel_states, f, indent=2)
            
            temp_file.replace(STATE_FILE)
            
        except Exception as e:
            self.logger.error("Error saving states", e)

def main():
    root = tk.Tk()
    try:
        app = YouTubeShuffler(root)
        root.mainloop()
    except Exception as e:
        print(f"Fatal error: {e}")
        traceback.print_exc()
        messagebox.showerror("Fatal Error", f"Application failed to start:\n\n{e}")

if __name__ == "__main__":
    main()