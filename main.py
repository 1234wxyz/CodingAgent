from agent.encoding import ensure_utf8_stdio

ensure_utf8_stdio()

from agent.app import main

if __name__ == "__main__":
    raise SystemExit(main())
