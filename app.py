from pathlib import Path
import os
import traceback

import streamlit as st

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


APP_TITLE = "Folder Code/Text to PDF"


COMMON_SKIP_DIRS = {
    ".git",
    ".svn",
    ".hg",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".idea",
    ".vscode",
}


COMMON_SKIP_FILES = {
    "uv.lock",
}


def find_monospace_font():
    possible_paths = [
        r"C:\Windows\Fonts\consola.ttf",
        r"C:\Windows\Fonts\DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]

    for font_path in possible_paths:
        if Path(font_path).exists():
            return font_path

    return None


def register_code_font():
    font_path = find_monospace_font()

    if font_path:
        try:
            pdfmetrics.registerFont(TTFont("CodeFont", font_path))
            return "CodeFont"
        except Exception:
            return "Courier"

    return "Courier"


def is_probably_binary(file_path: Path):
    try:
        with open(file_path, "rb") as file:
            chunk = file.read(4096)

        return b"\x00" in chunk

    except Exception:
        return True


def read_text_file(file_path: Path):
    raw_bytes = file_path.read_bytes()

    encodings = [
        "utf-8",
        "utf-8-sig",
        "utf-16",
        "cp1252",
        "latin-1",
    ]

    for encoding in encodings:
        try:
            return raw_bytes.decode(encoding), encoding
        except UnicodeDecodeError:
            continue

    return raw_bytes.decode("utf-8", errors="replace"), "utf-8-with-replacement"


def collect_files(
    source_folder: Path,
    output_folder: Path,
    include_hidden: bool,
    skip_common_dirs: bool,
):
    collected_files = []

    for root, dirs, filenames in os.walk(source_folder):
        root_path = Path(root)

        if skip_common_dirs:
            dirs[:] = [
                directory
                for directory in dirs
                if directory not in COMMON_SKIP_DIRS
            ]

        if not include_hidden:
            dirs[:] = [
                directory
                for directory in dirs
                if not directory.startswith(".")
            ]

        for filename in filenames:
            file_path = root_path / filename

            if filename.lower() in COMMON_SKIP_FILES:
                continue

            if not include_hidden and filename.startswith("."):
                continue

            try:
                resolved_file_path = file_path.resolve()
                resolved_output_folder = output_folder.resolve()

                if resolved_output_folder in resolved_file_path.parents:
                    continue

                collected_files.append(file_path)

            except Exception:
                continue

    collected_files.sort(key=lambda path: str(path).lower())
    return collected_files


def clean_pdf_text(text: str, font_name: str):
    text = text.replace("\t", "    ")
    text = text.replace("\r", "")

    if font_name == "Courier":
        text = text.encode("latin-1", errors="replace").decode("latin-1")

    return text


def create_pdf_from_folder(
    source_folder: Path,
    output_folder: Path,
    output_pdf_name: str,
    include_hidden: bool,
    skip_common_dirs: bool,
):
    output_folder.mkdir(parents=True, exist_ok=True)

    if not output_pdf_name.lower().endswith(".pdf"):
        output_pdf_name = f"{output_pdf_name}.pdf"

    output_pdf_path = output_folder / output_pdf_name

    files = collect_files(
        source_folder=source_folder,
        output_folder=output_folder,
        include_hidden=include_hidden,
        skip_common_dirs=skip_common_dirs,
    )

    font_name = register_code_font()

    page_width, page_height = A4

    left_margin = 35
    right_margin = 35
    top_margin = 40
    bottom_margin = 35

    font_size = 8
    line_height = 10

    usable_width = page_width - left_margin - right_margin
    char_width = pdfmetrics.stringWidth("M", font_name, font_size)
    max_chars_per_line = max(int(usable_width / char_width), 40)

    pdf = canvas.Canvas(str(output_pdf_path), pagesize=A4)
    pdf.setTitle(f"Folder Export - {source_folder.name}")

    y_position = page_height - top_margin
    page_number = 1

    skipped_files = []
    processed_files = 0

    def write_footer():
        pdf.setFont(font_name, 7)
        pdf.drawRightString(
            page_width - right_margin,
            bottom_margin / 2,
            f"Page {page_number}",
        )

    def new_page():
        nonlocal y_position, page_number

        write_footer()
        pdf.showPage()

        page_number += 1
        y_position = page_height - top_margin

    def ensure_space(lines_required=1):
        nonlocal y_position

        if y_position - lines_required * line_height < bottom_margin:
            new_page()

    def write_line(text="", bold=False):
        nonlocal y_position

        ensure_space(1)

        selected_font = font_name

        if bold and font_name == "Courier":
            selected_font = "Courier-Bold"

        pdf.setFont(selected_font, font_size)
        pdf.drawString(left_margin, y_position, text)

        y_position -= line_height

    def write_wrapped_line(text):
        cleaned_text = clean_pdf_text(text, font_name)

        if cleaned_text == "":
            write_line("")
            return

        for index in range(0, len(cleaned_text), max_chars_per_line):
            write_line(cleaned_text[index:index + max_chars_per_line])

    for file_path in files:
        try:
            if is_probably_binary(file_path):
                skipped_files.append((str(file_path), "Binary file skipped"))
                continue

            relative_path = file_path.relative_to(source_folder)
            content, encoding = read_text_file(file_path)

            processed_files += 1

            separator = "=" * min(max_chars_per_line, 90)

            ensure_space(6)

            write_line(separator, bold=True)
            write_line(f"FILE: {relative_path}", bold=True)
            write_line(f"ENCODING: {encoding}", bold=True)
            write_line(separator, bold=True)
            write_line("")

            lines = content.splitlines()

            if lines:
                for line in lines:
                    write_wrapped_line(line)
            else:
                write_line("[Empty file]")

            write_line("")
            write_line("")

        except Exception as error:
            skipped_files.append((str(file_path), str(error)))

    ensure_space(5)

    separator = "=" * min(max_chars_per_line, 90)

    write_line(separator, bold=True)
    write_line("EXPORT SUMMARY", bold=True)
    write_line(separator, bold=True)
    write_line(f"Project folder: {source_folder.name}")
    write_line(f"Text/code files processed: {processed_files}")

    write_footer()
    pdf.save()

    return output_pdf_path, processed_files, skipped_files


def main():
    st.set_page_config(
        page_title=APP_TITLE,
        layout="centered",
    )

    st.title(APP_TITLE)

    st.write(
        "Enter a folder path. This app recursively reads all text/code files "
        "and creates one combined PDF in the selected output folder."
    )

    source_folder_input = st.text_input(
        "Source folder path",
        placeholder=r"C:\VSCode\Your_Project",
    )

    output_folder_input = st.text_input(
        "Output folder path",
        placeholder=r"C:\VSCode\Your_Project\output",
    )

    output_pdf_name = st.text_input(
        "Output PDF file name",
        value="folder_code_export.pdf",
    )

    include_hidden = st.checkbox(
        "Include hidden files and folders",
        value=False,
    )

    skip_common_dirs = st.checkbox(
        "Skip common cache/build folders",
        value=True,
    )

    if st.button("Create PDF"):
        if not source_folder_input.strip():
            st.error("Please enter a source folder path.")
            return

        source_folder = Path(source_folder_input.strip())

        if not source_folder.exists():
            st.error("Source folder does not exist.")
            return

        if not source_folder.is_dir():
            st.error("Source path must be a folder.")
            return

        if output_folder_input.strip():
            output_folder = Path(output_folder_input.strip())
        else:
            output_folder = source_folder / "output"

        try:
            with st.spinner("Creating PDF..."):
                output_pdf_path, processed_files, skipped_files = create_pdf_from_folder(
                    source_folder=source_folder,
                    output_folder=output_folder,
                    output_pdf_name=output_pdf_name.strip() or "folder_code_export.pdf",
                    include_hidden=include_hidden,
                    skip_common_dirs=skip_common_dirs,
                )

            st.success("PDF created successfully.")

            st.write("Output PDF file:")
            st.code(output_pdf_path.name, language="text")

            st.write("Files processed:")
            st.write(processed_files)

        except Exception:
            st.error("Failed to create PDF.")
            st.code(traceback.format_exc(), language="text")


if __name__ == "__main__":
    main()