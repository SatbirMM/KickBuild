import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import subprocess
import re
import json
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import time

# Set the path to VsDevCmd.bat (Modify this if needed)
DEV_CMD_PATH = r'"C:\Program Files\Microsoft Visual Studio\2022\Professional\Common7\Tools\VsDevCmd.bat"'

# Configuration file to store selections
CONFIG_FILE = "config.json"

class SlnBuildApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MSBuild Optimizer")
        self.root.geometry("800x600")
        self.root.resizable(True, True)

        # Right Frame (Project List)
        self.right_frame = tk.Frame(root)
        self.right_frame.pack(side="right", expand=True, fill="both", padx=10, pady=10)

        # Timer Label
        self.timer_label = tk.Label(self.right_frame, text="Build Time: 00:00", fg="black")
        self.timer_label.pack(pady=5)

        # File watcher
        self.observer = Observer()
        self.event_handler = FileSystemEventHandler()
        self.event_handler.on_modified = self.on_file_modified

        # Initialize project selection as empty dictionary
        self.project_selection = {}
        self.build_process = None
        self.build_cancelled = False

        # Left Frame (Buttons)
        self.left_frame = tk.Frame(root, width=200, bg="#f0f0f0")
        self.left_frame.pack(side="left", fill="y")

        self.select_button = tk.Button(self.left_frame, text="Select .sln File", command=self.select_sln)
        self.select_button.pack(pady=20, padx=10, fill="x")

        self.check_all_button = tk.Button(self.left_frame, text="Check All", command=self.check_all, state=tk.DISABLED)
        self.check_all_button.pack(pady=5, padx=10, fill="x")

        self.uncheck_all_button = tk.Button(self.left_frame, text="Uncheck All", command=self.uncheck_all, state=tk.DISABLED)
        self.uncheck_all_button.pack(pady=5, padx=10, fill="x")

        self.build_button = tk.Button(self.left_frame, text="Build Selected", command=self.build_selected, state=tk.DISABLED)
        self.build_button.pack(pady=10, padx=10, fill="x")

        self.cancel_button = tk.Button(self.left_frame, text="Cancel Build", command=self.cancel_build, state=tk.DISABLED)
        self.cancel_button.pack(pady=5, padx=10, fill="x")

        # Right Frame (Project List)
        self.right_frame = tk.Frame(root)
        self.right_frame.pack(side="right", expand=True, fill="both", padx=10, pady=10)

        self.file_label = tk.Label(self.right_frame, text="No file selected", fg="gray")
        self.file_label.pack(pady=5)

        # Scrollable Project List
        self.canvas = tk.Canvas(self.right_frame)
        self.scrollbar = ttk.Scrollbar(self.right_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas)

        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Progress Bar
        self.progress_bar = ttk.Progressbar(self.right_frame, orient="horizontal", mode="indeterminate")
        self.progress_bar.pack(pady=20, fill="x")
        self.progress_bar.stop()

        self.sln_path = ""
        self.projects = []
        self.load_last_selection()

        # Add a checkbox to skip post-build actions
        self.skip_post_build_var = tk.BooleanVar()
        self.skip_post_build_checkbox = tk.Checkbutton(self.left_frame, text="Skip Post-Build Actions", variable=self.skip_post_build_var)
        self.skip_post_build_checkbox.pack(pady=5, padx=10, fill="x")

          # Initialize timer variables
        self.start_time = None
        self.timer_running = False


    def load_last_selection(self):
        """ Loads the last used .sln file and project selections from config.json """
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    self.sln_path = config.get("sln_path", "")
                    self.project_selection = config.get("selected_projects", {})

                    if self.sln_path and os.path.exists(self.sln_path):
                        self.file_label.config(text=os.path.basename(self.sln_path), fg="black")
                        self.load_projects()
            except json.JSONDecodeError:
                pass  # Ignore corrupted JSON

    def save_selection(self):
        """ Saves the current .sln file and selected projects to config.json """
        selected_projects = {name: var.get() for name, (var, _) in self.project_vars.items()}
        config = {
            "sln_path": self.sln_path,
            "selected_projects": selected_projects
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

    def select_sln(self):
        file_path = filedialog.askopenfilename(filetypes=[("Solution files", "*.sln")])
        if file_path:
            self.sln_path = file_path
            self.file_label.config(text=os.path.basename(file_path), fg="black")
            self.load_projects()
            self.save_selection()  # Save the new selection
        else:
            self.file_label.config(text="No file selected", fg="gray")
            self.build_button.config(state=tk.DISABLED)
            self.check_all_button.config(state=tk.DISABLED)
            self.uncheck_all_button.config(state=tk.DISABLED)

    def load_projects(self):
        """ Parses the .sln file to extract projects for 'SauronDebug X54' configuration recursively """
        self.projects.clear()
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        with open(self.sln_path, "r", encoding="utf-8") as f:
            sln_content = f.read()

        # Regular expression to find the project paths
        project_matches = re.findall(r'Project\(".*?"\) = "([^"]+)", "([^"]+)"', sln_content)
        if not project_matches:
            messagebox.showerror("Error", "No projects found in the solution!")
            return

        # Get all project files recursively from the directory of the .sln file
        sln_directory = os.path.dirname(self.sln_path)
        for root, dirs, files in os.walk(sln_directory):
            for file in files:
                if file in self.project_selection:
                    project_name = os.path.basename(file)
                    project_path = os.path.relpath(os.path.join(root, file), sln_directory)
                    self.projects.append((project_name, project_path))

        # Sort projects alphabetically
        self.projects.sort(key=lambda x: x[0])

        # Create checkboxes for the found project files
        self.project_vars = {}
        for name, path in self.projects:
            var = tk.BooleanVar(value=self.project_selection.get(name, True))
            chk = tk.Checkbutton(self.scrollable_frame, text=name, variable=var, command=self.save_selection)
            chk.pack(anchor="w", padx=5, pady=2)
            self.project_vars[name] = (var, path)

        self.build_button.config(state=tk.NORMAL)
        self.check_all_button.config(state=tk.NORMAL)
        self.uncheck_all_button.config(state=tk.NORMAL)

        # Start file watcher
        self.observer.schedule(self.event_handler, sln_directory, recursive=True)
        #self.observer.start()

    def check_all(self):
        """ Selects all projects """
        for var, _ in self.project_vars.values():
            var.set(True)
        self.save_selection()

    def uncheck_all(self):
        """ Deselects all projects """
        for var, _ in self.project_vars.values():
            var.set(False)
        self.save_selection()

    def update_timer(self):
        """ Updates the timer label with the elapsed time """
        if self.timer_running:
            elapsed_time = time.time() - self.start_time
            minutes, seconds = divmod(int(elapsed_time), 60)
            self.timer_label.config(text=f"Build Time: {minutes:02}:{seconds:02}")
            self.root.after(1000, self.update_timer)

    def build_selected(self):
        """ Builds only selected projects using MSBuild inside Visual Studio Developer Command Prompt """

        # Start the build timer
        self.start_time = time.time()
        self.timer_running = True
        self.update_timer()
        selected_projects = [path for name, (var, path) in self.project_vars.items() if var.get()]
        if not selected_projects:
            messagebox.showwarning("Warning", "No projects selected for build!")
            return

        # Change working directory to the solution folder
        sln_directory = os.path.dirname(self.sln_path)

        # Disable buttons and start the progress bar
        self.build_button.config(state=tk.DISABLED)
        self.check_all_button.config(state=tk.DISABLED)
        self.uncheck_all_button.config(state=tk.DISABLED)
        self.cancel_button.config(state=tk.NORMAL)
        self.progress_bar.start()

        # Initialize start times for each project
        self.project_start_times = {project: time.time() for project in selected_projects}

        # Run the build process in a separate thread to keep the UI responsive
        self.build_cancelled = False
        build_thread = threading.Thread(target=self.run_build, args=(selected_projects, sln_directory))
        build_thread.start()

    def run_build(self, selected_projects, sln_directory):
        """ Executes MSBuild commands in a separate thread to keep UI responsive """
        for project_path in selected_projects:
            if self.build_cancelled:
                break

            full_project_path = os.path.join(sln_directory, project_path)

            # Build command
            command = f'cmd /c "cd /d {sln_directory} && {DEV_CMD_PATH} && msbuild \"{full_project_path}\" /verbosity:minimal /p:PostBuildEventUseInBuild=false /p:PostBuildEvent=\" ECHO Hi.. \" /p:Configuration=\"SauronDebug\" /p:Platform=\"X64\""'
            command = f'cmd /c "cd /d {sln_directory} && {DEV_CMD_PATH} && msbuild \"{full_project_path}\" /m /verbosity:minimal /p:PostBuildEventUseInBuild=false /p:PostBuildEvent=\" ECHO Hi.. \" /p:Configuration=\"SauronDebug\" /p:Platform=\"X64\""'
   

            print (command)
           
            # Run the build command without showing popups
            try:
                subprocess.run(command, shell=True, check=True)
                self.mark_project_status(project_path, "green")
                
                # Skip post-build actions if the checkbox is selected
                if not self.skip_post_build_var.get():
                    self.perform_post_build_actions(full_project_path)
            except subprocess.CalledProcessError:
                self.mark_project_status(project_path, "red")
        # Stop the timer
        self.timer_running = False

        # After build finishes, re-enable the buttons and stop the progress bar
        self.progress_bar.stop()
        self.build_button.config(state=tk.NORMAL)
        self.check_all_button.config(state=tk.NORMAL)
        self.uncheck_all_button.config(state=tk.NORMAL)
        self.cancel_button.config(state=tk.DISABLED)

    def perform_post_build_actions(self, project_path):
        """ Perform post-build actions for the given project """
        # Add your post-build actions here
        self.copy_dll_exe_pdb_to_run_dir(project_path)

    def copy_dll_exe_pdb_to_run_dir(self, project_path):
        """ Copies the target file (dll/exe) and pdb (if Debug/SauronDebug) to the project's target directory """
        # Set environment variables
        env_vars = {
            "_ConfigurationName_": "SauronDebug",
            "_PlatformTarget_": "X64",
            "_ProjectName_": os.path.basename(project_path),
            "_TargetPath_": project_path,
            "_TargetDir_": os.path.dirname(project_path),
            "_TargetName_": os.path.splitext(os.path.basename(project_path))[0]
        }

        if env_vars["_ProjectName_"] == "Medmont.Studio.Installer":
            print("CopyDllExePdbToRunDir doesn't run on Medmont.Studio.Installer project. No action taken")
            return

        run_dirs = [
            "Studio\\CLR\Medmont.Studio.Installer\\bin\\"
            # Add other run directories here if needed
        ]

        conf_dir = os.path.join(env_vars["_PlatformTarget_"], env_vars["_ConfigurationName_"])

        sub_dir = ""
        project_sub_dirs = {
            "Medmont.DV2000.Alkeria": "ImageSource\\Alkeria",
            "Medmont.DV2000.Alkeria.Installer": "ImageSource\\Alkeria",
            "Medmont.DV2000.CanonED": "ImageSource\\CanonED",
            "Medmont.DV2000.CanonRC": "ImageSource\\CanonRC",
            "Medmont.DV2000.Inami": "ImageSource\\Inami",
            "Medmont.DV2000.Keeler": "ImageSource\\Keeler",
            "Medmont.DV2000.Keeler.Forms": "ImageSource\\Keeler",
            "Medmont.DV2000.NikonD100": "ImageSource\\NikonD100",
            "Medmont.DV2000.SunKingdom": "ImageSource\\SunKingdom",
            "Medmont.Video.Artray": "Video\\Artray",
            "Medmont.Video.AVT": "Video\\AVT",
            "Medmont.Video.AVT.Installer": "Video\\AVT",
            "Medmont.Video.E300": "Video\\E300",
            "Medmont.Video.E300C.uEye": "Video\\E300C.uEye",
            "Medmont.Video.E300C.uEye.Forms": "Video\\E300C.uEye",
            "Medmont.Video.FlashBus": "Video\\FlashBus",
            "Medmont.Video.Leutron": "Video\\Leutron",
            "Medmont.Video.Leutron.Installer": "Video\\Leutron",
            "Medmont.Video.Picolo": "Video\\Picolo",
            "Medmont.Video.PointGrey": "Video\\PointGrey",
            "Medmont.Video.PointGrey.Installer": "Video\\PointGrey",
            "Medmont.Video.uEye.Installer": "Video\\uEye",
            "Medmont.Video.E300C.Peak": "Video\\E300C.Peak",
            "Medmont.Video.Peak": "Video\\E300C.Peak",
            "Medmont.Video.E300C.Simulator": "Video\\E300C.Simulator",
            "Medmont.Video.Simulator": "Video\\E300C.Simulator"
        }

        sub_dir = project_sub_dirs.get(env_vars["_ProjectName_"], "")

        for run_dir in run_dirs:
            if not run_dir:
                continue
            # get parent dictionary of sln path
            run_dir = os.path.join(os.path.dirname(self.sln_path), run_dir)


          

            des_dir = os.path.join(run_dir, conf_dir, sub_dir)

            des_dir = os.path.join(os.path.dirname(self.sln_path), des_dir)
            if not os.path.exists(des_dir):
                os.makedirs(des_dir)

            print(f"Run directory: {run_dir}") # make it full path
            print(f"Destination: {des_dir}")

            # Copy target file
            self.copy_file(env_vars["_TargetPath_"], des_dir)

            # Copy PDB file if in Debug or SauronDebug configuration
            if env_vars["_ConfigurationName_"] in ["Debug", "SauronDebug"]:
                pdb_path = os.path.join(env_vars["_TargetDir_"], f"{env_vars['_TargetName_']}.pdb")
                self.copy_file(pdb_path, des_dir)

            # Additional file copies for specific projects
            if env_vars["_ProjectName_"] == "Medmont.Video.E300C.Simulator":
                self.copy_additional_files(env_vars["_TargetDir_"], des_dir)

    def copy_file(self, src, dest):
        """ Copies a file from src to dest """
        return;
        if os.path.exists(src):
            subprocess.run(["xcopy", "/Y", f'"{src}"', f'"{dest}"'], check=True)

    def mark_project_status(self, project_path, color):
        """ Marks the project status with a colored tick and time taken """
        end_time = time.time()
        start_time = self.project_start_times.get(project_path, end_time)
        time_taken = (end_time - start_time) / 60  # Convert to minutes

        for widget in self.scrollable_frame.winfo_children():
            if widget.cget("text") in project_path:
                widget.config(fg=color)
                widget.config(text=f"{widget.cget('text')} ({time_taken:.2f} min)")

    def copy_additional_files(self, src_dir, dest_dir):
        """ Copies additional files for specific projects """
        additional_files = [
            "Newtonsoft.Json.dll",
            "*.cfg",
            "images\\*",
            "ECF\\*"
        ]

        for file_pattern in additional_files:
            subprocess.run(["xcopy", "/Y", "/D", "/F", os.path.join(src_dir, file_pattern), dest_dir], check=True)

    def cancel_build(self):
        """ Cancels the ongoing build process """
        self.build_cancelled = True
        if self.build_process:
            self.build_process.terminate()

    def on_file_modified(self, event):
        """ Handles file modification events """
        self.load_projects()

if __name__ == "__main__":
    root = tk.Tk()
    app = SlnBuildApp(root)
    root.mainloop()
