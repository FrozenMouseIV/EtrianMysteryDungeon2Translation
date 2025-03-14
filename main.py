import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import csv
import os


# ---------------------------------------------
# Helper Function for SIR0 Pointer Offsets List
# (Used only by the full rebuild; not used in our in‑place update)
# ---------------------------------------------
def encode_ptr_offsets(ptr_list):
    encoded_bytes = bytearray()
    prev = 0
    for p in ptr_list:
        diff = p - prev
        prev = p
        groups = []
        while True:
            groups.insert(0, diff & 0x7F)
            if diff < 0x80:
                break
            diff >>= 7
        for i in range(len(groups) - 1):
            groups[i] |= 0x80
        encoded_bytes.extend(groups)
    encoded_bytes.append(0)
    return bytes(encoded_bytes)


# ---------------------------------------------
# SIR0 Base Class
# ---------------------------------------------
class Sir0:
    def __init__(self, file_bytes=None):
        self.padding_byte = 0x0
        self.resize_file_on_load = True
        self.relative_pointers = []
        self.file_contents = None
        self.content_header = None

        if file_bytes:
            self.create_file(file_bytes)

    def create_file(self, file_bytes: bytes):
        self.file_contents = file_bytes
        self.process_data()

    def process_data(self):
        file_bytes = self.file_contents
        # Read header information.
        self.header_offset = int.from_bytes(file_bytes[4:8], 'little')
        self.pointer_offset = int.from_bytes(file_bytes[8:12], 'little')
        self.content_header = file_bytes[self.header_offset:self.pointer_offset]
        self.header_padding = 0
        for i in range(self.header_offset + len(self.content_header) - 1, self.header_offset - 1, -1):
            if file_bytes[i] == self.padding_byte:
                self.header_padding += 1
            else:
                break
        self.content_header = file_bytes[
                              self.header_offset: self.header_offset + len(self.content_header) - self.header_padding]
        self.relative_pointers = self.decode_pointers(file_bytes[self.pointer_offset:])
        if self.resize_file_on_load:
            self.length = len(file_bytes) - len(self.relative_pointers) - len(self.content_header)

    def decode_pointers(self, pointer_section: bytes):
        relative_pointers = []
        is_constructing = False
        constructed_pointer = 0
        for byte in pointer_section:
            if byte >= 128:
                is_constructing = True
                constructed_pointer = (constructed_pointer << 7) | (byte & 0x7F)
            else:
                if is_constructing:
                    constructed_pointer = (constructed_pointer << 7) | (byte & 0x7F)
                    relative_pointers.append(constructed_pointer)
                    is_constructing = False
                    constructed_pointer = 0
                else:
                    if byte == 0:
                        break
                    relative_pointers.append(byte)
        return relative_pointers

    def read(self, offset, count):
        return self.file_contents[offset: offset + count]


# ---------------------------------------------
# MessageBinStringEntry Class
# ---------------------------------------------
class MessageBinStringEntry:
    def __init__(self, hash, entry, unknown, pointer):
        self.original_index = 0
        self.pointer = pointer
        self.entry = entry
        self.hash = hash
        self.unknown = unknown
        self.old_str_len = None  # Will be set after reading

    @property
    def hash_signed(self):
        if self.hash > 0x7fffffff:
            return self.hash - 0x100000000
        return self.hash

    def __str__(self):
        return f"{self.hash_signed}: {self.entry}"

    def get_string_bytes(self):
        # Not used for in-place update; provided for completeness.
        output = bytearray()
        skip = 0
        length = len(self.entry)
        count = 0
        while count < length:
            if skip > 0:
                skip -= 1
                count += 1
                continue
            char = self.entry[count]
            if char != '\r':
                if char == '\\' and count + 4 < length:
                    escape_string1 = self.entry[count + 1: count + 3]
                    escape_string2 = self.entry[count + 3: count + 5]
                    if self.is_hex(escape_string1) and self.is_hex(escape_string2):
                        output.append(int(escape_string2, 16))
                        output.append(int(escape_string1, 16))
                        skip = 4
                        count += 1
                        continue
                output.extend(char.encode('utf-16le'))
            count += 1
        output.extend(b'\x00\x00')
        return bytes(output)

    @staticmethod
    def is_hex(s):
        try:
            int(s, 16)
            return True
        except ValueError:
            return False


# ---------------------------------------------
# MessageBin Class (subclassing Sir0)
# ---------------------------------------------
class MessageBin(Sir0):
    def __init__(self, open_read_only=False):
        super().__init__()
        self.strings = []
        self.is_read_only = open_read_only

    def process_data(self):
        super().process_data()
        # The first 4 bytes of the content header is the string count.
        string_count = int.from_bytes(self.content_header[:4], 'little')
        # The next 4 bytes is a pointer to the string information block.
        string_info_pointer = int.from_bytes(self.content_header[4:8], 'little')

        for i in range(string_count):
            info_offset = string_info_pointer + i * 12
            string_pointer = int.from_bytes(self.read(info_offset, 4), 'little')
            string_hash = int.from_bytes(self.read(info_offset + 4, 4), 'little')
            unk = int.from_bytes(self.read(info_offset + 8, 4), 'little')

            s = []
            j = 0
            while True:
                two_bytes = self.read(string_pointer + j * 2, 2)
                if len(two_bytes) < 2:
                    break
                try:
                    ch = two_bytes.decode('utf-16le')
                except UnicodeDecodeError:
                    break
                if ch == '\x00':
                    break
                s.append(ch)
                j += 1
            text = "".join(s).strip()
            entry = MessageBinStringEntry(
                hash=string_hash,
                entry=text,
                unknown=unk,
                pointer=string_pointer
            )
            # Calculate and store the originally allocated length (including null terminator)
            entry.old_str_len = j * 2 + 2
            self.strings.append(entry)
        self.set_original_indexes(self.strings)

    def set_original_indexes(self, strings):
        # Sorting by pointer preserves the original order.
        for index, item in enumerate(sorted(strings, key=lambda x: x.pointer)):
            item.original_index = index


# ---------------------------------------------
# Parse Function (stores original file bytes)
# ---------------------------------------------
def parse_bin_file(file_bytes):
    mb = MessageBin(open_read_only=True)
    mb.create_file(file_bytes)
    return {
        "content_header_ptr": mb.header_offset,
        "pointer_list_ptr": mb.pointer_offset,
        "records": mb.strings,
        # Store a mutable copy of the original data:
        "original_bytes": bytearray(file_bytes)
    }


# ---------------------------------------------
# Main Tkinter Application
# ---------------------------------------------
class MessageBinEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Message Bin Editor")
        self.geometry("800x600")
        self.data = None  # Parsed data dictionary for single file processing
        self.current_file_path = None
        self.create_widgets()

    def create_widgets(self):
        # File menu setup.
        menubar = tk.Menu(self)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Open", command=self.open_file)
        filemenu.add_command(label="Save", command=self.save_file)
        filemenu.add_separator()
        filemenu.add_command(label="Export CSV", command=self.export_csv)
        filemenu.add_command(label="Import CSV", command=self.import_csv)
        filemenu.add_separator()
        # New batch-processing commands:
        filemenu.add_command(label="Max Export Folder", command=self.max_export_folder)
        filemenu.add_command(label="Max Import Folder", command=self.max_import_folder)
        menubar.add_cascade(label="File", menu=filemenu)
        self.config(menu=menubar)

        # Treeview setup.
        self.tree = ttk.Treeview(self, columns=("Index", "ID", "Entry"), show="headings")
        self.tree.heading("Index", text="Index")
        self.tree.heading("ID", text="ID")
        self.tree.heading("Entry", text="Entry")
        self.tree.column("Index", width=50, anchor="center")
        self.tree.column("ID", width=100, anchor="center")
        self.tree.column("Entry", width=600, anchor="w")
        self.tree.pack(fill=tk.BOTH, expand=True)

        # Enable editing on double click.
        self.tree.bind("<Double-1>", self.on_tree_double_click)

        # Vertical scrollbar.
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')

    def populate_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        if not self.data:
            return
        for record in self.data["records"]:
            self.tree.insert("", "end", values=(record.original_index, record.hash, record.entry))

    def open_file(self):
        file_path = filedialog.askopenfilename(
            title="Open .bin file",
            filetypes=[("BIN files", "*.bin"), ("All files", "*.*")]
        )
        if not file_path:
            return
        self.current_file_path = file_path
        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            self.data = parse_bin_file(file_bytes)
            self.populate_tree()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to parse file:\n{e}")
            self.data = None

    def save_file(self):
        """
        Instead of rebuilding the entire file,
        update the changed entries in the original file.
        This version automatically truncates or pads the new entry
        data so that exactly the originally allocated length is used.
        """
        if not self.data:
            messagebox.showerror("Error", "No data to save.")
            return
        orig_bytes = self.data.get("original_bytes")
        if not orig_bytes:
            messagebox.showerror("Error", "Original file data missing.")
            return

        for record in self.data["records"]:
            allocated = record.old_str_len
            # Maximum bytes available for the text (reserve 2 bytes for null terminator)
            max_text_bytes = allocated - 2
            if max_text_bytes % 2 != 0:
                max_text_bytes -= 1
            # Encode the new text without the null terminator.
            text_bytes = record.entry.encode("utf-16-le")
            # Truncate if necessary.
            if len(text_bytes) > max_text_bytes:
                text_bytes = text_bytes[:max_text_bytes]
            new_bytes = text_bytes + b'\x00\x00'
            if len(new_bytes) < allocated:
                new_bytes += b'\x00' * (allocated - len(new_bytes))
            start = record.pointer
            end = record.pointer + allocated
            orig_bytes[start:end] = new_bytes

        save_path = filedialog.asksaveasfilename(
            title="Save .bin file",
            initialfile=os.path.basename(self.current_file_path) if self.current_file_path else "untitled.bin",
            defaultextension=".bin",
            filetypes=[("BIN files", "*.bin"), ("All files", "*.*")]
        )
        if not save_path:
            return
        try:
            with open(save_path, "wb") as f:
                f.write(orig_bytes)
            messagebox.showinfo("Saved", "File saved successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save file:\n{e}")

    def export_csv(self):
        if not self.data:
            messagebox.showerror("Error", "No data loaded.")
            return
        file_path = filedialog.asksaveasfilename(
            title="Export CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["Index", "ID", "Entry"])
                for record in self.data["records"]:
                    writer.writerow([record.original_index, record.hash, record.entry])
            messagebox.showinfo("Export CSV", "CSV exported successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Exporting CSV failed:\n{e}")

    def import_csv(self):
        if not self.data:
            messagebox.showerror("Error", "No data loaded.")
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
                for row in reader:
                    idx = int(row["Index"])
                    for record in self.data["records"]:
                        if record.original_index == idx:
                            record.entry = row["Entry"]
                            break
            self.populate_tree()
            messagebox.showinfo("Import CSV", "CSV imported successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Importing CSV failed:\n{e}")

    def max_export_folder(self):
        folder = filedialog.askdirectory(title="Select folder for max export")
        if not folder:
            return
        # Process all .bin files in the folder.
        for filename in os.listdir(folder):
            if filename.lower().endswith(".bin"):
                full_path = os.path.join(folder, filename)
                try:
                    with open(full_path, "rb") as f:
                        file_bytes = f.read()
                    data = parse_bin_file(file_bytes)
                    csv_name = os.path.splitext(filename)[0] + ".csv"
                    csv_path = os.path.join(folder, csv_name)
                    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
                        writer = csv.writer(csvfile)
                        writer.writerow(["Index", "ID", "Entry"])
                        for record in data["records"]:
                            writer.writerow([record.original_index, record.hash, record.entry])
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to export {filename}:\n{e}")
        messagebox.showinfo("Max Export", "All .bin files have been exported to CSV.")

    def max_import_folder(self):
        folder = filedialog.askdirectory(title="Select folder for max import")
        if not folder:
            return
        # For each .csv file, locate the corresponding .bin file and update it.
        for filename in os.listdir(folder):
            if filename.lower().endswith(".csv"):
                csv_path = os.path.join(folder, filename)
                # The .bin file is assumed to have the same base name.
                bin_filename = os.path.splitext(filename)[0] + ".bin"
                bin_path = os.path.join(folder, bin_filename)
                if not os.path.exists(bin_path):
                    continue
                try:
                    with open(bin_path, "rb") as f:
                        file_bytes = f.read()
                    data = parse_bin_file(file_bytes)
                    with open(csv_path, "r", newline="", encoding="utf-8") as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            idx = int(row["Index"])
                            for record in data["records"]:
                                if record.original_index == idx:
                                    record.entry = row["Entry"]
                                    break
                    # Update the original_bytes in-place.
                    orig_bytes = data["original_bytes"]
                    for record in data["records"]:
                        allocated = record.old_str_len
                        max_text_bytes = allocated - 2
                        if max_text_bytes % 2 != 0:
                            max_text_bytes -= 1
                        text_bytes = record.entry.encode("utf-16-le")
                        if len(text_bytes) > max_text_bytes:
                            text_bytes = text_bytes[:max_text_bytes]
                        new_bytes = text_bytes + b'\x00\x00'
                        if len(new_bytes) < allocated:
                            new_bytes += b'\x00' * (allocated - len(new_bytes))
                        start = record.pointer
                        end = record.pointer + allocated
                        orig_bytes[start:end] = new_bytes
                    with open(bin_path, "wb") as f:
                        f.write(orig_bytes)
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to import {filename}:\n{e}")
        messagebox.showinfo("Max Import", "CSV files imported and .bin files updated.")

    def on_tree_double_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return
        col = self.tree.identify_column(event.x)
        col_index = int(col.replace("#", "")) - 1
        # Only allow editing the "Entry" column (index 2)
        if col_index != 2:
            return
        x, y, width, height = self.tree.bbox(item_id, col)
        entry_edit = tk.Entry(self.tree)

        def save_edit(evt):
            new_val = entry_edit.get()
            self.tree.set(item_id, column="Entry", value=new_val)
            values = self.tree.item(item_id, "values")
            record_index = int(values[0])
            for record in self.data["records"]:
                if record.original_index == record_index:
                    record.entry = new_val
                    break
            entry_edit.destroy()

        entry_edit.place(x=x, y=y, width=width, height=height)
        entry_edit.insert(0, self.tree.item(item_id, "values")[2])
        entry_edit.focus()
        entry_edit.bind("<Return>", save_edit)
        entry_edit.bind("<FocusOut>", lambda e: entry_edit.destroy())


if __name__ == "__main__":
    app = MessageBinEditor()
    app.mainloop()
