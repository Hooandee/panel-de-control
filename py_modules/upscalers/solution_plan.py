"""Capabilities of the composed game configuration, never evidence of execution."""
from . import catalog


def resolve(gpu, analysis, recipe=None, generation=9, engine="optiscaler", route=None, dependencies_ready=False):
    declared = getattr(recipe, "effective_api", None)
    forced = {value for argument in getattr(recipe, "args", ())
              if (value := {"-dx11": "d3d11", "-d3d11": "d3d11", "-dx12": "d3d12",
                            "-d3d12": "d3d12", "-vulkan": "vulkan"}.get(argument.lower()))}
    if declared:
        forced.add(declared)
    detected = set(analysis.get("apis", ())) & {"d3d11", "d3d12", "vulkan"}
    conflict = len(forced) > 1
    api = next(iter(forced)) if len(forced) == 1 else next(iter(detected)) if not forced and len(detected) == 1 else None
    source = "recipe" if forced else "detected" if api else "unknown"
    owner = getattr(recipe, "quality_owner", "panel") if engine == "optiscaler" else "game"
    recommended = getattr(recipe, "recommended_input", None)
    reconciled = bool(engine == "optiscaler" and dependencies_ready and recommended and getattr(recipe, "dependencies", ()))
    offered = (catalog.fg_plan(gpu, analysis.get("inputs", {}), getattr(recipe, "fg", None),
                               generation, ["d3d12"], analysis.get("streamline"), route)
               if engine == "optiscaler" else None)
    fg = None
    if engine == "optiscaler" and not conflict:
        fg = catalog.fg_plan(gpu, analysis.get("inputs", {}), getattr(recipe, "fg", None),
                             generation, [api or "unknown"], analysis.get("streamline"), route)
        if fg and api != "d3d12":
            routes = {key: value for key, value in fg["routes"].items()
                      if key != "optiscaler" and value.get("input") not in ("fsrfg", "xefg")}
            if routes:
                selected = route if route in routes else next(iter(routes))
                fg = {**routes[selected], "route": selected, "routes": routes}
            else:
                fg = None
    return {"input_reconciled": reconciled, "recommended_input": recommended, "effective_api": api, "api_source": source,
            "quality": {"owner": owner, "reason": "recipe_quality_game" if owner == "game" else None},
            "fg_plan": fg, "offered_fg_plan": offered, "blocked_reason": None,
            "warning_reason": "recipe_api_conflict" if conflict else None,
            "dependencies": list(getattr(recipe, "dependencies", ())) if engine == "optiscaler" else [],
            "recipe_revision": getattr(recipe, "catalog_revision", None)}


def requested_fg(plan, choice):
    if choice.get("fg") != "on":
        return None
    offered = plan["offered_fg_plan"]
    explicit = choice.get("fg_route")
    if not explicit:
        # Without a route of the user's own, a known non-DX12 game only gets one that works with its API.
        if plan["fg_plan"] or plan.get("effective_api") not in (None, "d3d12"):
            return plan["fg_plan"]
        explicit = (offered or {}).get("route")
    return catalog.fg_route_plan(offered, explicit) if offered and explicit in offered["routes"] else None
