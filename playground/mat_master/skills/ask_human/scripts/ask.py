"""
Ask Human Script: print a question to the user and return their reply.

Usage:
  python ask.py "Your question"
  python ask.py "Your question" "Optional context"
  echo "Your question" | python ask.py

Output: prints the question (and context if provided) to stdout, then reads one
line via input() and prints that line as the result for the caller.
"""

import sys


def main() -> None:
    if len(sys.argv) >= 2:
        question = sys.argv[1]
        context = sys.argv[2] if len(sys.argv) >= 3 else None
    else:
        try:
            question = sys.stdin.read().strip() or "Please provide input:"
            context = None
        except Exception:
            question = "Please provide input:"
            context = None

    print(question)
    if context:
        print(f"Context: {context}")
    print("(waiting for your reply)", flush=True)
    reply = input().strip()
    print(reply)


if __name__ == "__main__":
    main()
