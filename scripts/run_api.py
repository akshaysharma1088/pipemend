"""Run every PipeMend prompt against models through their APIs, several times.

Each call sends the exact text of prompts/<case>.txt as a single user message:
no system prompt, no tools, no other context. One JSON file is written per
response, so an interrupted run can be resumed with the same command.

    export ANTHROPIC_API_KEY=...
    python3 scripts/run_api.py --out runs_api --reps 5

An open-weights model can be added through any OpenAI-compatible endpoint:

    export OPENAI_COMPAT_API_KEY=...
    python3 scripts/run_api.py --out runs_api --reps 5 --provider openai \
        --base-url https://<host>/v1 --models open=<model id>

Layout: <out>/<label>/rep<k>/<case>.json and <out>/manifest-<provider>.json.
`--mock` replays the recorded responses in runs/ so the pipeline can be tested
without an API key; its numbers are not new measurements.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

DEFAULT_MODELS = "haiku=claude-haiku-5-5,sonnet=claude-sonnet-5-5,opus=claude-opus-5-5"
MAX_TOKENS = 16000  # caps everything the model emits; one retry at double if a reply is cut off


def call_anthropic(client, model, prompt, cap, temperature):
    import anthropic
    transient = (anthropic.APIConnectionError, anthropic.APITimeoutError,
                 anthropic.InternalServerError, anthropic.RateLimitError)
    extra = {} if temperature is None else {"temperature": temperature}
    for i in range(6):
        try:
            with client.messages.stream(model=model, max_tokens=cap,
                                        messages=[{"role": "user", "content": prompt}], **extra) as s:
                msg = s.get_final_message()
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            return dict(text=text, served=msg.model, stop=msg.stop_reason,
                        tokens_in=msg.usage.input_tokens, tokens_out=msg.usage.output_tokens)
        except transient as exc:
            if i == 5:
                raise
            print(f"  {type(exc).__name__}, retrying in {5 * 2 ** i}s", flush=True)
            time.sleep(5 * 2 ** i)


def call_openai_compat(base_url, key, model, prompt, cap, temperature):
    body = {"model": model, "max_tokens": cap, "messages": [{"role": "user", "content": prompt}]}
    if temperature is not None:
        body["temperature"] = temperature
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    for i in range(6):
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                d = json.load(resp)
            ch = d["choices"][0]
            u = d.get("usage") or {}
            stop = {"length": "max_tokens", "stop": "end_turn"}.get(ch.get("finish_reason"), ch.get("finish_reason"))
            return dict(text=ch["message"].get("content") or "", served=d.get("model", model), stop=stop,
                        tokens_in=u.get("prompt_tokens"), tokens_out=u.get("completion_tokens"))
        except urllib.error.HTTPError as exc:
            if exc.code not in (408, 409, 429, 500, 502, 503, 504, 529) or i == 5:
                raise RuntimeError(f"HTTP {exc.code}: {exc.read()[:300]!r}") from exc
        except (urllib.error.URLError, TimeoutError):
            if i == 5:
                raise
        print(f"  transient error, retrying in {5 * 2 ** i}s", flush=True)
        time.sleep(5 * 2 ** i)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--models", default=DEFAULT_MODELS, help="comma-separated label=model id")
    ap.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    ap.add_argument("--base-url", default="", help="OpenAI-compatible endpoint, ending in /v1")
    ap.add_argument("--key-env", default="OPENAI_COMPAT_API_KEY", help="environment variable with the endpoint's key")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--temperature", type=float, default=None, help="default: the provider's default")
    ap.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--cases", default="", help="comma-separated prompt names (default: all 82)")
    ap.add_argument("--prompts", default="prompts", help="folder of prompt files")
    ap.add_argument("--mock", action="store_true", help="replay runs/<label>/ instead of calling a model")
    a = ap.parse_args()

    models = dict(x.strip().split("=", 1) for x in a.models.split(",") if x.strip())
    names = sorted(os.path.basename(f)[:-4] for f in glob.glob(os.path.join(a.prompts, "*.txt")))
    if a.cases:
        names = [n for n in names if n in {c.strip() for c in a.cases.split(",")}]
    if not names:
        sys.exit("no prompts selected; run from the repository root")

    client = key = None
    if a.mock:
        print("MOCK run: replaying recorded responses. Not a new measurement.")
    elif a.provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("Set ANTHROPIC_API_KEY, or use --mock to test the pipeline.")
        import anthropic  # pip install anthropic
        client = anthropic.Anthropic(max_retries=6)
    else:
        key = os.environ.get(a.key_env)
        if not key or not a.base_url:
            sys.exit(f"--provider openai needs --base-url and the key in ${a.key_env}.")

    cut_off, served, t0 = {}, {}, time.time()

    def one(job):
        label, rep, name = job
        path = os.path.join(a.out, label, f"rep{rep}", name + ".json")
        if os.path.exists(path):
            return
        prompt = open(os.path.join(a.prompts, name + ".txt")).read()
        t = time.time()
        if a.mock:
            d = json.load(open(f"runs/{label}/{name}.json"))
            r = dict(text=d["raw_response"], served="mock:" + d["served_models"][0], stop="end_turn",
                     tokens_in=len(prompt) // 4, tokens_out=d["usage"]["output"])
            cap = a.max_tokens
        else:
            for cap in (a.max_tokens, 2 * a.max_tokens):
                r = (call_anthropic(client, models[label], prompt, cap, a.temperature) if a.provider == "anthropic"
                     else call_openai_compat(a.base_url, key, models[label], prompt, cap, a.temperature))
                if r["stop"] != "max_tokens":
                    break
            else:
                cut_off[label] = cut_off.get(label, 0) + 1
        served.setdefault(label, set()).add(r["served"])
        rec = dict(tier=label, case=name, rep=rep, condition={"NN-": "no_change_notes", "DK-": "no_change_notes+duplicate_profile"}.get(name[:3], "notes"),
                   requested_model=models[label], served_model=r["served"], provider="mock" if a.mock else a.provider,
                   temperature=a.temperature, max_tokens=cap, stop_reason=r["stop"],
                   usage={"input": r["tokens_in"], "output": r["tokens_out"]},
                   seconds=round(time.time() - t, 2), raw_response=r["text"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        json.dump(rec, open(tmp, "w"), indent=1)
        os.replace(tmp, path)

    for rep in range(a.reps):
        for label in models:
            with ThreadPoolExecutor(max_workers=a.workers) as pool:
                list(pool.map(one, [(label, rep, n) for n in names]))
            print(f"rep {rep} {label:8s} {len(names)} responses [{time.time() - t0:.0f}s]", flush=True)

    manifest = dict(mode="MOCK" if a.mock else "REAL", provider=a.provider, base_url=a.base_url or None,
                    models_requested=models, models_served={k: sorted(v) for k, v in served.items()},
                    temperature="provider default" if a.temperature is None else a.temperature,
                    max_tokens=a.max_tokens, replies_cut_off_after_retry=cut_off, reps=a.reps,
                    n_prompts=len(names), prompts=a.prompts,
                    message_format="one user message = the prompt file; no system prompt, no tools",
                    python=sys.version.split()[0], finished_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    json.dump(manifest, open(os.path.join(a.out, f"manifest-{a.provider}.json"), "w"), indent=1)
    print("wrote", os.path.join(a.out, f"manifest-{a.provider}.json"))


if __name__ == "__main__":
    main()
