import tkinter as tk
from tkinter import ttk, filedialog
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
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Add new items
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