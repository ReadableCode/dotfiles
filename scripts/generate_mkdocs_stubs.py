# %%
# Imports #

import os
import warnings

from config_scripts import docs_dir, src_dir

warnings.filterwarnings("ignore")

# %%
# Imports #


def delete_old_stubs(output_dir, dry_run=False):
    if os.path.exists(output_dir):
        print(f"Deleting {output_dir}")
        if not dry_run:
            os.system(f"rm -r {output_dir}")


def remove_python_stubs_from_index(dry_run=False):
    with open(os.path.join(docs_dir, "index.md"), "r") as f:
        lines = f.readlines()

    if dry_run:
        print("only keeping lines:")
        for line in lines:
            if "/src/" not in line:
                print(line)
    else:
        with open(os.path.join(docs_dir, "index.md"), "w") as f:
            for line in lines:
                if "/src/" not in line:
                    f.write(line)


def generate_docs_for_directory(directory, output_dir, dry_run=False):
    num_python_docs = 1
    for root, dirs, files in os.walk(directory):
        for file in files:
            if (
                file.endswith(".py")
                and not file.startswith("__")
                and "-checkpoint" not in file
            ):
                output_file_path = (
                    os.path.join(root, file)
                    .replace(directory, output_dir)
                    .replace(".py", ".md")
                )
                module_rel_path = os.path.join(root, file).replace(
                    os.path.dirname(directory), ""
                )
                module_name = os.path.basename(file).replace(".py", "")
                module_name = (
                    module_name.replace("_", " ")
                    .title()
                    .replace("Url", "URL")
                    .replace("Pdf", "PDF")
                )
                module_rel_path_dot_notation = (
                    module_rel_path.replace(os.sep, ".").lstrip(".").replace(".py", "")
                )
                module_path = os.path.join(file).rstrip(".py")
                os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
                print(f"Writing {output_file_path}")
                write_string = f"# {module_name} Documentation\n\n"
                write_string_2 = f"::: {module_rel_path_dot_notation}\n"
                print(write_string)
                print(write_string_2)
                if not dry_run:
                    with open(output_file_path, "w") as f:
                        f.write(write_string)
                        f.write(write_string_2)

                module_dot_notation_path = output_file_path.replace(
                    docs_dir, ""
                ).replace(os.sep, "/")
                write_line = (
                    f"{num_python_docs}. [{module_path}](.{module_dot_notation_path})\n"
                )
                print(f"Writing {write_line} to index.md")
                if not dry_run:
                    with open(os.path.join(docs_dir, "index.md"), "a") as f:
                        f.write(write_line)
                num_python_docs += 1


# %%
# Main #


if __name__ == "__main__":
    dry_run = False

    delete_old_stubs(os.path.join(docs_dir, "src"), dry_run=dry_run)
    remove_python_stubs_from_index(dry_run=dry_run)
    generate_docs_for_directory(src_dir, os.path.join(docs_dir, "src"), dry_run=dry_run)


# %%
