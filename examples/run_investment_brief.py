"""Compatibility entry point: uses the same service as the interactive CLI."""
import sys
from financial_assistant.cli import main

if __name__ == '__main__':
    if '--once' not in sys.argv:
        sys.argv.append('--once')
    main()
