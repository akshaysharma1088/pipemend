"""How runs/ was produced. Each case was run as an isolated sub-agent session; this
script reads the session transcripts (JSONL), and extracts each agent's final answer, model id, token usage and tool calls from
its transcript, without printing the transcript. Writes runs/<tier>/<case>.json."""
import glob, json, os, re, sys
TASKS = sys.argv[1] if len(sys.argv) > 1 else "transcripts"  # directory of sub-agent JSONL transcripts
done = 0
for f in sorted(glob.glob(f"{TASKS}/*.output")):
    recs = []
    for l in open(f):
        try:
            recs.append(json.loads(l))
        except json.JSONDecodeError:
            pass
    case = tier = None
    models, tools, text, usage = set(), [], None, {"input": 0, "output": 0, "cache_read": 0, "cache_create": 0}
    for d in recs:
        m = d.get("message") if isinstance(d.get("message"), dict) else None
        if d.get("type") == "user" and m and case is None:
            c = m.get("content")
            s = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c if isinstance(x, dict))
            mm = re.search(r"inbox/([A-Z0-9a-z-]+)\.txt", s)
            if mm:
                case = mm.group(1)
        if d.get("type") == "assistant" and m:
            tier = tier or d.get("requestedModel")
            if m.get("model"):
                models.add(m["model"])
            u = m.get("usage") or {}
            usage["input"] += u.get("input_tokens", 0) or 0
            usage["output"] += u.get("output_tokens", 0) or 0
            usage["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
            usage["cache_create"] += u.get("cache_creation_input_tokens", 0) or 0
            for blk in m.get("content", []) if isinstance(m.get("content"), list) else []:
                if blk.get("type") == "tool_use":
                    tools.append({"name": blk.get("name"), "input": blk.get("input")})
                if blk.get("type") == "text" and blk.get("text", "").strip():
                    text = blk["text"]
    if not case or text is None:
        continue
    tier_name = next((t for t in ("haiku", "sonnet", "opus") if t in str(tier).lower()), str(tier))
    os.makedirs(f"runs/{tier_name}", exist_ok=True)
    out = f"runs/{tier_name}/{case}.json"
    json.dump({"tier": tier_name, "case": case, "requested_model": tier, "served_models": sorted(models),
               "tool_calls": tools, "usage": usage, "raw_response": text,
               "transcript": os.path.basename(f)}, open(out, "w"), indent=1)
    done += 1
print("collected", done)
for t in ("haiku", "sonnet", "opus"):
    print(t, len(glob.glob(f"runs/{t}/*.json")))
