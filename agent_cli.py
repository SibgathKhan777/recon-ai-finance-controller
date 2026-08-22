"""Interactive terminal chat for the AI Finance Controller.

Run: python agent_cli.py

No API key required -- routing and answers are grounded in real
reconciliation output by default. Set ANTHROPIC_API_KEY to let the Q&A
agent phrase answers to open-ended questions via Claude instead of the
built-in keyword responses; the specialist that handles your message is
decided the same way either way.

Try:
  run reconciliation
  what's our match rate
  why didn't RZP123456789 settle    (use a real ref from reports/matches.csv)
  cash forecast for 14 days
  show duplicate exceptions
  triage exceptions
  verify claim: I never received my payout for RZP123456789
"""
from agents.orchestrator import smart_handle as handle

BANNER = """
AI Finance Controller -- multi-agent terminal
Agents online: Reconciliation, Settlement Q&A, Cash Forecaster, Exception & Anomaly, Claim Verification
Type a question or command. Type 'exit' to quit.
""".strip()


def main():
    print(BANNER)
    print()
    while True:
        try:
            message = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not message:
            continue
        if message.lower() in {"exit", "quit"}:
            break
        print(handle(message))
        print()


if __name__ == "__main__":
    main()
