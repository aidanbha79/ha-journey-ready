"""Build the HACS release asset with runtime files at the archive root."""

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def build(output):
    root = Path(__file__).resolve().parents[1] / "custom_components" / "journey_ready"
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if (
                path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix not in (".pyc", ".pyo")
            ):
                archive.write(path, path.relative_to(root).as_posix())
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", default="dist/journey_ready.zip")
    print(build(parser.parse_args().output))
