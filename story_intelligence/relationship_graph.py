"""NetworkX story graph built from the database.

Nodes: characters, episodes, events.  Edges:
    appears_in      character -> episode     (script fact: they speak in it)
    appears_with    character -- character   (script fact: they share scenes; weight = scenes)
    participates_in character -> event       (from logline extraction; carries confidence)
    in_episode      event -> episode
    related_to / conflicts_with / ...  character -> character (LLM, from loglines; carries confidence)
"""
from __future__ import annotations

import networkx as nx

from database import repositories as R

CONFLICT_RELATIONS = {"rivals", "conflict"}


def build_graph(con, project_id: int, min_lines: int = 3) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    chars = [c for c in R.get_characters(con, project_id) if c["n_lines"] >= min_lines]
    names = {c["name"] for c in chars}
    for c in chars:
        g.add_node(c["name"], kind="character", n_lines=c["n_lines"], aliases=c["aliases"],
                   first_ep=c["first_ep"], last_ep=c["last_ep"])
        for ep, n in c["episodes"].items():
            g.add_node(f"Ep{ep}", kind="episode", number=ep)
            g.add_edge(c["name"], f"Ep{ep}", kind="appears_in", weight=n, confidence=1.0)
    for r in R.get_relationships(con, project_id):
        if r["a"] in names and r["b"] in names:
            kind = "appears_with" if r["relation"] == "appears_with" else (
                "conflicts_with" if r["relation"] in CONFLICT_RELATIONS else "related_to")
            g.add_edge(r["a"], r["b"], kind=kind, label=r["relation"], confidence=r["confidence"],
                       evidence=r["evidence"], episodes=r["episodes"], source=r["source"])
    for e in R.get_events(con, project_id):
        node = f"event:{e['id']}"
        g.add_node(node, kind="event", description=e["description"], event_type=e["event_type"],
                   importance=e["importance"], verified=bool(e["verified"]), confidence=e["confidence"],
                   episode=e["episode"])
        g.add_edge(node, f"Ep{e['episode']}", kind="in_episode", confidence=1.0)
        for c in e["characters"]:
            if c in names:
                g.add_edge(c, node, kind="participates_in", confidence=e["confidence"])
    return g


def character_view(g: nx.MultiDiGraph, name: str) -> dict:
    """Everything the editor needs about one character."""
    if name not in g:
        return {}
    eps = sorted(g.nodes[v]["number"] for _, v, d in g.out_edges(name, data=True) if d["kind"] == "appears_in")
    partners: dict[str, dict] = {}
    for u, v, d in list(g.out_edges(name, data=True)) + list(g.in_edges(name, data=True)):
        other = v if u == name else u
        if g.nodes[other].get("kind") != "character":
            continue
        p = partners.setdefault(other, {"shared_scenes": 0, "relations": []})
        if d["kind"] == "appears_with":
            p["shared_scenes"] = int(d.get("evidence", "0").split()[1]) if d.get("evidence", "").startswith("shared") else 0
        else:
            p["relations"].append({"relation": d["label"], "confidence": d["confidence"], "evidence": d["evidence"]})
    events = [{"episode": g.nodes[v]["episode"], "description": g.nodes[v]["description"],
               "event_type": g.nodes[v]["event_type"], "importance": g.nodes[v]["importance"],
               "verified": g.nodes[v]["verified"]}
              for _, v, d in g.out_edges(name, data=True) if d["kind"] == "participates_in"]
    return {"name": name, **{k: g.nodes[name][k] for k in ("n_lines", "aliases", "first_ep", "last_ep")},
            "episodes": eps, "connections": dict(sorted(partners.items(), key=lambda kv: -kv[1]["shared_scenes"])),
            "events": sorted(events, key=lambda e: (e["episode"], -e["importance"]))}


def character_subgraph(g: nx.MultiDiGraph, focus: str | None, max_chars: int = 25) -> nx.Graph:
    """A simple undirected character network for drawing (optionally centred on one character)."""
    chars = sorted([n for n, d in g.nodes(data=True) if d["kind"] == "character"],
                   key=lambda n: -g.nodes[n]["n_lines"])[:max_chars]
    if focus and focus in g:
        neigh = {v for _, v, d in g.out_edges(focus, data=True) if g.nodes[v]["kind"] == "character"} | \
                {u for u, _, d in g.in_edges(focus, data=True) if g.nodes[u]["kind"] == "character"}
        chars = [focus] + [c for c in chars if c in neigh][:max_chars - 1]
    h = nx.Graph()
    for c in chars:
        h.add_node(c, n_lines=g.nodes[c]["n_lines"])
    for u, v, d in g.edges(data=True):
        if u in h and v in h and u != v:
            prev = h.get_edge_data(u, v, {})
            w = prev.get("weight", 0) + (d.get("weight") or (1 if d["kind"] == "appears_with" else 0))
            labels = prev.get("labels", set()) | ({d["label"]} if d.get("label") and d["kind"] != "appears_with" else set())
            h.add_edge(u, v, weight=w, labels=labels)
    return h


def to_pyvis_html(h: nx.Graph, focus: str | None = None, height: str = "560px") -> str:
    """Interactive network (presentation only). Colours follow the studio design tokens."""
    from pyvis.network import Network
    # monochrome: node brightness = importance; conflicts are DASHED edges (shape, not colour)
    bg, text, node, focus_c, edge, conflict = "#111111", "#FFFFFF", "#8C8C8C", "#FFFFFF", "#3A3A3A", "#B3B3B3"
    net = Network(height=height, width="100%", bgcolor=bg, font_color=text, cdn_resources="in_line")
    net.barnes_hut(gravity=-6000, spring_length=140)
    top = max([d["n_lines"] for _, d in h.nodes(data=True)] or [1])
    for n, d in h.nodes(data=True):
        net.add_node(n, label=n.title(), title=f"{n.title()}: {d['n_lines']} lines",
                     size=8 + 26 * d["n_lines"] / top, borderWidth=2 if n == focus else 1,
                     color={"background": focus_c if n == focus else node, "border": "#FFFFFF" if n == focus else "#555555",
                            "highlight": {"background": focus_c, "border": node}},
                     font={"face": "Inter, Segoe UI, sans-serif", "size": 13, "color": text})
    for u, v, d in h.edges(data=True):
        lab = ", ".join(sorted(d["labels"]))
        is_conflict = any(x in CONFLICT_RELATIONS for x in d["labels"])
        net.add_edge(u, v, value=max(1, d["weight"]), title=(lab + " · " if lab else "") + f"{d['weight']} shared scenes",
                     color=conflict if is_conflict else edge, dashes=is_conflict)
    html = net.generate_html()
    # vis-network is inlined from the installed package (works offline); drop pyvis's unused remote Bootstrap
    # and dead node_modules references so the graph makes no network requests.
    import re
    html = re.sub(r'<link[^>]*(?:bootstrap|node_modules|lib/bindings)[^>]*>', "", html)
    html = re.sub(r'<script[^>]*(?:bootstrap|node_modules|lib/bindings)[^>]*>\s*</script>', "", html)
    return html.replace("</head>", "<style>html,body{margin:0;overflow:hidden;background:%s} #mynetwork{border:none!important;"
                                  "background:%s!important} .card{border:none!important;background:%s!important}"
                                  "</style></head>" % (bg, bg, bg), 1)
