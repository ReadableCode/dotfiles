# Installing and Using Pandoc

## Installation

To install Pandoc, run the following command:

- Linux

```bash
sudo apt install pandoc texlive texlive-latex-base
```

- Windows

```bash
choco install pandoc
choco install typst --confirm
```

## Usage

To convert a Markdown file to a PDF file, run the following command:

- Linux

```bash
pandoc filename.md -o filename.pdf
```

- Windows

```bash
pandoc filename.md -o filename.pdf --pdf-engine=typst
```
