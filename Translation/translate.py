import os
import re
from transformers import MarianMTModel, MarianTokenizer
import torch
import pandas as pd

# Activate cuda if available.
if torch.cuda.is_available():
    dev = "cuda"
    print("cuda")
else:
    dev = "cpu"
device = torch.device(dev)

# Activate the translation model.
model_name1 = "Helsinki-NLP/opus-mt-jap-en"
tokenizer1 = MarianTokenizer.from_pretrained(model_name1)
model1 = MarianMTModel.from_pretrained(model_name1)
model1.to(device)


def translate(texto):
    translated_text = ""
    if texto is not None:
        inputs = tokenizer1.encode(texto, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model1.generate(inputs, num_beams=4, max_length=10, early_stopping=True)
            translated_text = tokenizer1.decode(outputs[0], skip_special_tokens=True)
    return translated_text

# Global variable for the target column name.
column_name = 'Entry'


def translate_japanese(japanese_text_list):
    """
    Given a list of Japanese text strings,
    return a list containing their translations.
    """
    translated_text = []
    for text in japanese_text_list:
        translated_text.append(translate(text))
    return translated_text


def replace_japanese_text(strings):
    """
    Replace Japanese text segments (Hiragana, Katakana, Kanji)
    for non-string values by skipping them, and return a list with
    the same order, leaving non-string values (and None) unchanged.
    """
    # Regex pattern for Japanese characters.
    pattern = re.compile(r'[\u3040-\u30FF\u4E00-\u9FAF]+')

    # Collect Japanese segments only from cells that are strings.
    all_japanese_segments = []
    for s in strings:
        if isinstance(s, str):
            all_japanese_segments.extend(pattern.findall(s))

    # Translate unique segments only.
    unique_segments = list(set(all_japanese_segments))
    translations = translate_japanese(unique_segments)

    # Build a mapping of original Japanese text to its translation.
    translation_map = {orig: trans for orig, trans in zip(unique_segments, translations)}

    replaced_strings = []
    for s in strings:
        # If s is not a string, we leave it unchanged.
        if not isinstance(s, str):
            replaced_strings.append(s)
        else:
            def replace_match(match):
                orig = match.group(0)
                return translation_map.get(orig, orig)
            replaced_string = pattern.sub(replace_match, s)
            replaced_strings.append(replaced_string)

    return replaced_strings


def replace_entry_column(csv_file: str, new_strings: list, output: str = "modified.csv"):
    """
    Read a CSV file, replace the 'Entry' column with new_strings,
    and then save the modified DataFrame to the output file.
    """
    df = pd.read_csv(csv_file, encoding='utf-8')

    if column_name not in df.columns:
        raise ValueError(f"The CSV file {csv_file} does not contain an '{column_name}' column.")

    if len(new_strings) != len(df):
        raise ValueError(
            f"Length mismatch: the CSV file {csv_file} has {len(df)} rows, but new_strings contains {len(new_strings)} elements."
        )

    df[column_name] = new_strings
    df.to_csv(output, index=False, encoding='utf-8')
    print(f"Modified CSV saved as {output}")


def process_csv_file(input_path, output_path):
    """
    Process a single CSV file:
    1. Reads the 'Entry' column.
    2. Replaces Japanese text segments with their translations.
    3. Writes the modified data back to a new CSV file.
    """
    # Read the CSV file into a DataFrame using the same method everywhere.
    df = pd.read_csv(input_path, encoding='utf-8')

    # Extract the 'Entry' column data as a list.
    column_data = df[column_name].tolist()

    print(f"Processing file: {input_path}")

    # Translate and replace Japanese text in the 'Entry' column.
    replaced_data = replace_japanese_text(column_data)

    # Check that the replaced list has the same number of elements as rows.
    if len(replaced_data) != len(df):
        raise ValueError(
            f"Length mismatch: the DataFrame has {len(df)} rows, but replaced_data contains {len(replaced_data)} elements."
        )

    # Replace the 'Entry' column with the new strings.
    df[column_name] = replaced_data

    # Save the DataFrame to an output CSV.
    df.to_csv(output_path, index=False, encoding='utf-8')
    print(f"Modified CSV saved as {output_path}")


# Define the input and output folders.
input_folder = 'CSV/Original'
output_folder = os.path.join(input_folder, 'Changed')

# Ensure that the output folder exists.
os.makedirs(output_folder, exist_ok=True)

# Process each CSV file in the input folder.
for filename in os.listdir(input_folder):
    input_file = os.path.join(input_folder, filename)

    # Process only files (ignore directories) that end with '.csv'.
    if os.path.isfile(input_file) and filename.lower().endswith('.csv'):
        output_file = os.path.join(output_folder, filename)
        process_csv_file(input_file, output_file)
