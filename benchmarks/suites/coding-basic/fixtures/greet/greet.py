#!/usr/bin/env python3
import argparse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    args = parser.parse_args()
    print(f"Hello, {args.name}")


if __name__ == "__main__":
    main()
