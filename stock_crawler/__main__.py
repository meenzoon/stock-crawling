import sys

from .cli import app


def main(argv: list[str] | None = None) -> None:
    app(args=argv)


if __name__ == "__main__":
    main(sys.argv[1:])
