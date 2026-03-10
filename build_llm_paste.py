import os

def create_llm_paste():
    output_file = "llm_paste.md"
    target_dirs = ["app", "static", "docs"]
    root_files = ["CLAUDE.md", "README.md", "requirements.txt", ".gitignore"]
    skip_files = {
        "llm_paste.md", "build_llm_paste.py", "blog.db", "tools.txt",
        "tools.json", "original_writer.py", "requirements_new.txt",
        "generate_ui.py", "generate_ui_leveric.py", "main_history.txt",
        "fix_db.py",
    }
    skip_dirs = {"__pycache__", "venv", ".venv", ".git", ".github", ".claude", ".vscode", ".pytest_cache"}
    allowed_extensions = {".py", ".html", ".js", ".css", ".md", ".txt"}

    with open(output_file, 'w', encoding='utf-8') as outfile:
        outfile.write("# Ares Engine — Complete Project Audit\n\n")
        outfile.write("This document contains every source file in the Ares Engine project.\n")
        outfile.write("Generated for LLM context ingestion.\n\n")

        # ── Section 1: Project Tree ──
        outfile.write("## 1. Project Structure\n```text\nares-engine/\n")

        def print_tree(directory, prefix=""):
            try:
                entries = sorted(os.listdir(directory))
            except PermissionError:
                return
            entries = [e for e in entries if e not in skip_dirs and not e.endswith('.pyc')]
            for i, entry in enumerate(entries):
                path = os.path.join(directory, entry)
                is_last = (i == len(entries) - 1)
                connector = "└── " if is_last else "├── "
                outfile.write(f"{prefix}{connector}{entry}\n")
                if os.path.isdir(path):
                    extension = "    " if is_last else "│   "
                    print_tree(path, prefix + extension)

        for d in target_dirs:
            if os.path.exists(d):
                outfile.write(f"├── {d}/\n")
                print_tree(d, "│   ")
        # Root files
        for rf in root_files:
            if os.path.exists(rf):
                outfile.write(f"├── {rf}\n")
        outfile.write("```\n")

        # ── Section 2: Root Config Files ──
        outfile.write("\n## 2. Root Configuration Files\n")
        for rf in root_files:
            if os.path.exists(rf):
                ext = os.path.splitext(rf)[1]
                lang = {"py": "python", ".md": "markdown", ".txt": "text"}.get(ext, ext.lstrip(".") or "text")
                try:
                    with open(rf, 'r', encoding='utf-8') as infile:
                        content = infile.read()
                    outfile.write(f"\n### {rf}\n```{lang}\n{content}\n```\n")
                except Exception as e:
                    print(f"Skipping {rf}: {e}")

        # ── Section 3: All Source Files ──
        outfile.write("\n## 3. Source Code\n")

        for root, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for file in sorted(files):
                if file in skip_files:
                    continue
                filepath = os.path.join(root, file)
                ext = os.path.splitext(file)[1]
                if ext not in allowed_extensions:
                    continue
                # Skip root files (already printed above)
                if root in (".", ".\\") and file in root_files:
                    continue
                lang = "python" if ext == ".py" else ext.lstrip(".")
                try:
                    with open(filepath, 'r', encoding='utf-8') as infile:
                        content = infile.read()
                    display_path = filepath.replace(".\\", "").replace("\\/", "/").replace("\\", "/")
                    outfile.write(f"\n### {display_path}\n```{lang}\n{content}\n```\n")
                except Exception as e:
                    print(f"Skipping {filepath}: {e}")

    print(f"✅ Generated {output_file}")
    size_kb = os.path.getsize(output_file) / 1024
    print(f"   Size: {size_kb:.1f} KB")

if __name__ == "__main__":
    create_llm_paste()

