LUCIDA — SUBMISSION
An AI workforce for a small shop in Dhaka.

Repository: https://github.com/EsmeAbha/Business_Marketing_Analysis_LLM


WHAT IS IN THIS FOLDER
----------------------

1 - How Lucida Works.pdf      The technical reference. Start here.
                              How the multi-agent system is arranged and
                              why, what each of the eight specialists does,
                              and which external API is called for what.
                              4 pages.

2 - Project README.pdf        The repository README: setup, the screens,
                              where data lives, configuration, and an
                              honest account of what works and what is
                              waiting on credentials.

3 - Deployment Guide.pdf      What the app needs from a host, why the usual
                              serverless platforms are the wrong shape for
                              it, and three ways to put it online.

sources/                      The markdown and HTML the PDFs were rendered
                              from, so any of them can be regenerated when
                              the code changes.


THE SHORT VERSION
-----------------

One supervisor routes work to eight specialists — market research, product
vision, pricing, stock, ad creative, customer engagement, delivery and
reporting. They share one memory of the business, and the run stops for the
owner's approval before anything irreversible: publishing an ad, spending
money, booking a courier.

Built as a LangGraph state machine. Every shop's data lives in its own
SQLite database, isolated by file rather than by an owner column, so a
forgotten filter cannot leak one business into another.

  Python 3.12 · LangGraph · Starlette · SQLite · 45 modules · 22 tables


RUNNING IT
----------

    python -m venv .venv
    .venv\Scripts\pip install -r requirements.txt
    copy .env.example .env          (then add GROQ_API_KEY)
    python serve.py

Open http://127.0.0.1:8000

Tests:  python tests/test_workforce.py


WHAT IS LIVE, AND WHAT IS NOT
-----------------------------

Working, verified against real APIs:
  · Chat with saved conversations, and photo understanding
  · Web research that asks where to search before spending anything
  · Ad generation and editing
  · Product catalogue with weights
  · Delivery quoting and booking through Pathao's live merchant API
  · The live workforce graph, with direct task assignment
  · A service admin view across every shop on the installation

Built and tested, waiting on credentials rather than code:
  · Messenger, Facebook, Instagram — need a Meta app and App Review
  · YouTube — needs an OAuth client
  · Steadfast — needs a merchant key pair
  · Email verification — needs SMTP

Known weak:
  · Ad artwork, while it runs on the free keyless image model

Anything not connected runs against a simulated adapter that is labelled as
such everywhere it appears. Nothing simulated is ever written to a shop's
records as though a real customer sent it.
