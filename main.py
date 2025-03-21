import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import csv
import os
import clr
from System import Environment
from System.Threading import Thread, ThreadStart, ApartmentState

# Add reference to the required DLL
clr.AddReference('SkyEditor.ROMEditor.Windows')

from SkyEditor.ROMEditor.MysteryDungeon.PSMD import MessageBin, MessageBinStringEntry
from System.Collections.ObjectModel import ObservableCollection
from SkyEditor.Core.IO import GenericFile
from SkyEditor.IO.FileSystem import PhysicalFileSystem


class MessageBinEditor:
    def __init__(self, root):
        self.root = root
        self.bin = None
        self.current_file = None
        self.file_system = PhysicalFileSystem()

        # Setup UI
        self.setup_gui()

    def setup_gui(self):
        self.root.title("Message Bin Editor")

        # Create treeview with scrollbars
        self.tree_frame = ttk.Frame(self.root)
        self.tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.tree = ttk.Treeview(self.tree_frame, columns=('ID', 'Index', 'Entry'), show='headings')
        self.tree.heading('ID', text='ID')
        self.tree.heading('Index', text='Index')
        self.tree.heading('Entry', text='Entry')
        self.tree.column('ID', width=100, anchor=tk.W)
        self.tree.column('Index', width=50, anchor=tk.W)
        self.tree.column('Entry', width=400, anchor=tk.W)

        vsb = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self.tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        self.tree_frame.grid_rowconfigure(0, weight=1)
        self.tree_frame.grid_columnconfigure(0, weight=1)

        # Button frame
        self.button_frame = ttk.Frame(self.root)
        self.button_frame.pack(fill=tk.X, padx=5, pady=5)

        self.open_btn = ttk.Button(self.button_frame, text="Open", command=self.open_file)
        self.open_btn.pack(side=tk.LEFT, padx=2)

        self.save_btn = ttk.Button(self.button_frame, text="Save", command=self.save_file)
        self.save_btn.pack(side=tk.LEFT, padx=2)

        self.export_csv_btn = ttk.Button(self.button_frame, text="Export CSV", command=self.export_csv)
        self.export_csv_btn.pack(side=tk.LEFT, padx=2)

        self.import_csv_btn = ttk.Button(self.button_frame, text="Import CSV", command=self.import_csv)
        self.import_csv_btn.pack(side=tk.LEFT, padx=2)

        # New buttons for mass operations
        self.max_export_btn = ttk.Button(self.button_frame, text="Max Export Folder", command=self.max_export_folder)
        self.max_export_btn.pack(side=tk.LEFT, padx=2)

        self.max_import_btn = ttk.Button(self.button_frame, text="Max Import Folder", command=self.max_import_folder)
        self.max_import_btn.pack(side=tk.LEFT, padx=2)

        # Entry editor
        self.editor_frame = ttk.LabelFrame(self.root, text="Entry Editor")
        self.editor_frame.pack(fill=tk.BOTH, padx=5, pady=5)

        self.entry_text = tk.Text(self.editor_frame, wrap=tk.WORD, height=5)
        self.entry_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.update_btn = ttk.Button(self.editor_frame, text="Update Entry", command=self.update_entry)
        self.update_btn.pack(side=tk.RIGHT, padx=5, pady=5)

        # Bind selection event
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)

    def open_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("BIN Files", "*.bin")])
        if file_path:
            self.current_file = file_path
            self.load_bin_file(file_path)

    def load_bin_file(self, path):
        self.bin = MessageBin()
        self.bin.OpenFile(path, self.file_system).Wait()
        self.populate_tree()

    def populate_tree(self):
        # Clear the treeview items
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Populate treeview with data from BIN
        for entry in self.bin.Strings:
            self.tree.insert('', 'end', values=(
                entry.Hash,
                entry.OriginalIndex,
                entry.Entry
            ))

    def on_tree_select(self, event):
        selected = self.tree.selection()
        if selected:
            item = self.tree.item(selected[0])
            self.entry_text.delete(1.0, tk.END)
            self.entry_text.insert(tk.END, item['values'][2])

    def update_entry(self):
        selected = self.tree.selection()
        if not selected or not self.bin:
            return

        new_text = self.entry_text.get(1.0, tk.END).strip()
        item = self.tree.item(selected[0])
        original_index = item['values'][1]
        entry_hash = item['values'][0]

        # Find and update the corresponding entry
        for entry in self.bin.Strings:
            if entry.Hash == entry_hash and entry.OriginalIndex == original_index:
                entry.Entry = new_text
                break

        # Update treeview
        self.tree.item(selected[0], values=(entry_hash, original_index, new_text))

    def save_file(self):
        if self.bin and self.current_file:
            self.bin.Save(self.current_file, self.file_system).Wait()

    def export_csv(self):
        if not self.bin:
            messagebox.showwarning("No Data", "No BIN file is loaded.")
            return

        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if file_path:
            with open(file_path, mode='w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(['ID', 'Index', 'Entry'])  # Write header
                for entry in self.bin.Strings:
                    writer.writerow([entry.Hash, entry.OriginalIndex, entry.Entry])
            messagebox.showinfo("Export Successful", f"Data exported to {file_path}")

    def import_csv(self):
        if not self.bin:
            messagebox.showerror("Error", "No BIN file loaded.")
            return

        file_path = filedialog.askopenfilename(
            title="Import CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", newline="", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                if reader.fieldnames is None:
                    messagebox.showerror("Error", "CSV file is empty or missing a header.")
                    return

                # Ensure the required columns exist.
                required_columns = ["Index", "Entry"]
                missing_columns = [col for col in required_columns if col not in reader.fieldnames]
                if missing_columns:
                    messagebox.showerror("Error", f"CSV file is missing column(s): {', '.join(missing_columns)}")
                    return

                # Build a lookup dictionary for fast access (O(1) per row)
                entry_lookup = {entry.OriginalIndex: entry for entry in self.bin.Strings}

                for row in reader:
                    idx_text = row.get("Index", "").strip()
                    if not idx_text:
                        continue
                    try:
                        idx = int(idx_text)
                    except ValueError as e:
                        messagebox.showwarning("Warning", f"Skipping row due to invalid Index value: {row}")
                        continue

                    entry_text = row.get("Entry", "").strip()
                    if idx in entry_lookup:
                        entry_lookup[idx].Entry = entry_text
                    else:
                        messagebox.showwarning("Warning", f"No matching entry found for Index: {idx}")

            self.populate_tree()  # Refresh the table
            messagebox.showinfo("Import CSV", "CSV imported successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Importing CSV failed:\n{e}")

    def max_export_folder(self):
        """
        Iterates over all .bin files in the selected folder,
        exports each to a CSV with the same base name in the same folder.
        """
        folder = filedialog.askdirectory(title="Select Folder with BIN Files")
        if not folder:
            return

        count = 0
        for filename in os.listdir(folder):
            if filename.lower().endswith('.bin'):
                file_path = os.path.join(folder, filename)
                try:
                    bin_obj = MessageBin()
                    bin_obj.OpenFile(file_path, self.file_system).Wait()
                    base_name = os.path.splitext(filename)[0]
                    csv_path = os.path.join(folder, base_name + '.csv')
                    with open(csv_path, mode='w', newline='', encoding='utf-8') as csvfile:
                        writer = csv.writer(csvfile)
                        writer.writerow(['ID', 'Index', 'Entry'])
                        for entry in bin_obj.Strings:
                            writer.writerow([entry.Hash, entry.OriginalIndex, entry.Entry])
                    count += 1
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to export {file_path}:\n{e}")
        messagebox.showinfo("Max Export Folder", f"Exported {count} BIN file(s) to CSV.")

    def max_import_folder(self):
        """
        Iterates over all .csv files in the selected folder.
        For each CSV file, looks for a matching .bin file (by base name) in the same folder,
        updates its entries from the CSV, and saves the .bin file.
        """
        folder = filedialog.askdirectory(title="Select Folder with CSV Files")
        if not folder:
            return

        count = 0
        for filename in os.listdir(folder):
            if filename.lower().endswith('.csv'):
                csv_path = os.path.join(folder, filename)
                base_name = os.path.splitext(filename)[0]
                bin_path = os.path.join(folder, base_name + '.bin')
                if not os.path.exists(bin_path):
                    messagebox.showwarning("Warning", f"BIN file not found for {csv_path}")
                    continue
                try:
                    bin_obj = MessageBin()
                    bin_obj.OpenFile(bin_path, self.file_system).Wait()
                    with open(csv_path, "r", newline="", encoding="utf-8") as csvfile:
                        reader = csv.DictReader(csvfile)
                        if reader.fieldnames is None:
                            messagebox.showerror("Error", f"CSV file {csv_path} is empty or missing a header.")
                            continue
                        required_columns = ["Index", "Entry"]
                        missing_columns = [col for col in required_columns if col not in reader.fieldnames]
                        if missing_columns:
                            messagebox.showerror("Error",
                                                 f"CSV file {csv_path} is missing column(s): {', '.join(missing_columns)}")
                            continue

                        entry_lookup = {entry.OriginalIndex: entry for entry in bin_obj.Strings}
                        for row in reader:
                            idx_text = row.get("Index", "").strip()
                            if not idx_text:
                                continue
                            try:
                                idx = int(idx_text)
                            except ValueError:
                                continue
                            entry_text = row.get("Entry", "").strip()
                            if idx in entry_lookup:
                                entry_lookup[idx].Entry = entry_text
                            else:
                                messagebox.showwarning("Warning", f"No matching entry in {bin_path} for index {idx}")

                    bin_obj.Save(bin_path, self.file_system).Wait()
                    count += 1
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to import CSV {csv_path} into BIN file {bin_path}:\n{e}")
        messagebox.showinfo("Max Import Folder", f"Imported CSV into {count} BIN file(s).")


# Required to handle STA threading for .NET interoperability
def start_app():
    root = tk.Tk()
    app = MessageBinEditor(root)
    root.mainloop()


if __name__ == '__main__':
    thread = Thread(ThreadStart(start_app))
    thread.ApartmentState = ApartmentState.STA
    thread.Start()
    thread.Join()
