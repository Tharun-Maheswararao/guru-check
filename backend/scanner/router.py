"""Routes a user's question to the NPC into one kind, using a Decisions API choice question.

The API layer uses the route to pick which saved numbers or video moments to ground the answer in.
"""

from typing import Callable

from backend import llm

ROUTES = {
    "trade": "Asks about a specific trade or moment: why it bought or sold, what happened on a date.",
    "performance": "Asks about overall results: returns, final balance, drawdown, win rate, best or worst year.",
    "period": "Asks how the strategy did in a specific period or event, e.g. 'would you survive 2022?'.",
    "comparison": "Asks how it compares to holding the market or to the random traders, or about luck.",
    "rules": "Asks what the strategy's rules are or how it decides to enter, exit, or stop out.",
    "video": "Asks what the guru said or showed in the video, or about the original claims.",
    "other": "Small talk or anything not about this strategy, its results, or its video.",
}

QUESTION = {
    "route": {
        "type": "choice",
        "instructions": "A user is talking to a trading strategy character. What is the user asking about?",
        "criteria": ROUTES,
    }
}


def route(user_question: str, decide: Callable = llm.decide) -> dict:
    answer = decide(user_question, QUESTION)["route"]
    return {"route": answer["choice"], "confidence": answer.get("confidence"),
            "probabilities": answer.get("probabilities", {})}
