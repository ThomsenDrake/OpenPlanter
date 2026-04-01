"""Investigation resolver for LLM-driven session-to-investigation matching.

This module resolves which investigation a session belongs to when no
--investigation-id is explicitly provided. It uses LLM inference to match
the user's objective against known investigations, then presents the user
with a confirmation prompt.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


@dataclass
class InvestigationChoice:
    """Represents a choice for investigation context."""
    investigation_id: str | None  # None = generic/one-off
    is_new: bool
    label: str  # Human-readable name


def list_investigations(workspace: Path) -> list[dict[str, Any]]:
    """Scan the workspace to build a catalog of known investigations.

    This function:
    - Loads .openplanter/ontology.json if it exists
    - Scans .openplanter/sessions/*/investigation_state.json for distinct investigations
    - Returns a list of dicts with id, label, session_count, entity_count, last_active

    Args:
        workspace: Path to the workspace root directory

    Returns:
        List of investigation metadata dicts, deduplicated by investigation ID.
        Empty list if no investigations found.
    """
    workspace = workspace.expanduser().resolve()
    openplanter_dir = workspace / ".openplanter"

    if not openplanter_dir.exists():
        return []

    investigations: dict[str, dict[str, Any]] = {}

    # Load ontology.json if it exists
    ontology_path = openplanter_dir / "ontology.json"
    if ontology_path.exists():
        try:
            ontology_data = json.loads(ontology_path.read_text(encoding="utf-8"))
            if isinstance(ontology_data, dict):
                indexes = ontology_data.get("indexes", {})
                if isinstance(indexes, dict):
                    by_investigation = indexes.get("by_investigation", {})
                    if isinstance(by_investigation, dict):
                        for inv_id, inv_data in by_investigation.items():
                            if not isinstance(inv_data, dict):
                                continue
                            investigations[str(inv_id)] = {
                                "id": str(inv_id),
                                "label": _derive_label(inv_id, inv_data),
                                "session_count": inv_data.get("session_count", 0),
                                "entity_count": inv_data.get("entity_count", 0),
                                "claim_count": inv_data.get("claim_count", 0),
                                "last_active": inv_data.get("last_active", ""),
                                "objective": inv_data.get("objective", ""),
                            }
        except (json.JSONDecodeError, OSError):
            pass

    # Scan sessions for investigation_state.json files
    sessions_dir = openplanter_dir / "sessions"
    if sessions_dir.exists():
        for session_dir in sessions_dir.iterdir():
            if not session_dir.is_dir():
                continue
            inv_state_path = session_dir / "investigation_state.json"
            if not inv_state_path.exists():
                continue

            try:
                state_data = json.loads(inv_state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            if not isinstance(state_data, dict):
                continue

            inv_id = state_data.get("active_investigation_id")
            if not isinstance(inv_id, str) or not inv_id.strip():
                continue

            inv_id = inv_id.strip()
            objective = state_data.get("objective", "")
            updated_at = state_data.get("updated_at", "")
            entities = state_data.get("entities", {})
            claims = state_data.get("claims", {})

            if inv_id not in investigations:
                investigations[inv_id] = {
                    "id": inv_id,
                    "label": _derive_label(inv_id, {"objective": objective}),
                    "session_count": 1,
                    "entity_count": len(entities) if isinstance(entities, dict) else 0,
                    "claim_count": len(claims) if isinstance(claims, dict) else 0,
                    "last_active": updated_at,
                    "objective": objective,
                }
            else:
                # Update counts and last_active
                investigations[inv_id]["session_count"] = investigations[inv_id].get("session_count", 0) + 1
                entity_count = len(entities) if isinstance(entities, dict) else 0
                investigations[inv_id]["entity_count"] = investigations[inv_id].get("entity_count", 0) + entity_count
                claim_count = len(claims) if isinstance(claims, dict) else 0
                investigations[inv_id]["claim_count"] = investigations[inv_id].get("claim_count", 0) + claim_count

                # Update last_active if this session is more recent
                existing_last = investigations[inv_id].get("last_active", "")
                if updated_at and (not existing_last or updated_at > existing_last):
                    investigations[inv_id]["last_active"] = updated_at

    return list(investigations.values())


def _derive_label(inv_id: str, data: dict[str, Any]) -> str:
    """Derive a human-readable label from investigation data."""
    # Try objective first
    objective = data.get("objective", "")
    if isinstance(objective, str) and objective.strip():
        # Truncate to reasonable length
        label = objective.strip()
        if len(label) > 60:
            label = label[:57] + "..."
        return label

    # Fall back to ID with some formatting
    return inv_id


def infer_investigation(
    objective: str,
    investigations: list[dict[str, Any]],
    llm_call: Callable[[str], str],
) -> dict[str, Any]:
    """Use LLM to classify the objective against known investigations.

    Args:
        objective: The user's question/objective
        investigations: List of investigation metadata dicts from list_investigations()
        llm_call: Callable that takes a prompt string and returns a response string

    Returns:
        Dict with keys: match (investigation_id | "new" | "generic"),
        confidence (0.0-1.0), reasoning (str)
    """
    if not investigations:
        return {"match": "generic", "confidence": 1.0, "reasoning": "No existing investigations to match against"}

    # Build the prompt
    inv_lines = []
    for i, inv in enumerate(investigations, 1):
        inv_id = inv.get("id", "unknown")
        label = inv.get("label", inv_id)
        session_count = inv.get("session_count", 0)
        entity_count = inv.get("entity_count", 0)
        claim_count = inv.get("claim_count", 0)
        last_active = inv.get("last_active", "unknown")
        inv_lines.append(
            f'{i}. "{inv_id}" - Sessions: {session_count}, Entities: {entity_count}, '
            f'Claims: {claim_count}, Last active: {last_active}\n   Label: {label}'
        )

    inv_list = "\n".join(inv_lines)

    prompt = f"""Given the user's question/objective and the list of existing investigations, determine which investigation this most likely belongs to, or whether it's a new investigation or a one-off query.

User objective: "{objective}"

Available investigations:
{inv_list}

Respond with ONLY a JSON object (no markdown, no explanation):
{{"match": "investigation_id_here" | "new" | "generic", "confidence": 0.9, "reasoning": "brief explanation"}}"""

    try:
        response = llm_call(prompt)
    except Exception:
        return {"match": "generic", "confidence": 0.0, "reasoning": "LLM call failed"}

    # Parse the JSON response
    response = response.strip()

    # Try to extract JSON if wrapped in markdown code blocks
    if "```" in response:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response)
        if match:
            response = match.group(1).strip()

    try:
        parsed = json.loads(response)
    except json.JSONDecodeError:
        return {"match": "generic", "confidence": 0.0, "reasoning": f"Failed to parse LLM response: {response[:100]}"}

    if not isinstance(parsed, dict):
        return {"match": "generic", "confidence": 0.0, "reasoning": "LLM response was not a JSON object"}

    match_value = parsed.get("match", "generic")
    confidence = parsed.get("confidence", 0.5)
    reasoning = parsed.get("reasoning", "No reasoning provided")

    # Validate match value
    if match_value not in ("new", "generic"):
        # Check if it matches a known investigation ID
        known_ids = {inv.get("id") for inv in investigations}
        if match_value not in known_ids:
            # Fall back to generic
            match_value = "generic"
            reasoning = f"LLM suggested unknown investigation ID, defaulting to generic. Original reasoning: {reasoning}"

    # Validate confidence
    try:
        confidence = float(confidence)
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.5

    return {
        "match": match_value,
        "confidence": confidence,
        "reasoning": str(reasoning) if reasoning else "No reasoning provided",
    }


def _slugify(text: str) -> str:
    """Convert text to a slug suitable for investigation ID."""
    # Lowercase and replace non-alphanumeric with dashes
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())
    # Remove leading/trailing dashes
    slug = slug.strip("-")
    # Limit length
    if len(slug) > 40:
        slug = slug[:40].rstrip("-")
    # Ensure non-empty
    if not slug:
        slug = "investigation"
    return slug


def resolve_investigation(
    workspace: Path,
    objective: str | None,
    llm_call: Callable[[str], str] | None,
    interactive: bool = True,
    default_investigation_id: str | None = None,
) -> str | None:
    """Main entry point for investigation resolution.

    Orchestrates the full resolution flow:
    1. If objective is None/empty, return default
    2. List known investigations
    3. If no investigations or no LLM, return default
    4. Use LLM to infer investigation match
    5. If interactive, present confirmation prompt
    6. Return chosen investigation_id (or None for generic)

    Args:
        workspace: Path to the workspace root
        objective: The user's objective (from --task or TUI input)
        llm_call: Callable for LLM inference, or None to skip inference
        interactive: If True, prompt user for confirmation
        default_investigation_id: Default ID to return if no inference possible

    Returns:
        Investigation ID string, or None for generic/one-off query
    """
    # Step a: If objective is None or empty, return default
    if not objective or not objective.strip():
        return default_investigation_id

    # Step b: List known investigations
    investigations = list_investigations(workspace)

    # If no investigations found, return None (no context needed)
    if not investigations:
        return None

    # Step c: If no LLM callable, return default
    if llm_call is None:
        return default_investigation_id

    # Step d: Call LLM for inference
    inference = infer_investigation(objective, investigations, llm_call)
    match_value = inference.get("match", "generic")
    confidence = inference.get("confidence", 0.0)
    reasoning = inference.get("reasoning", "")

    # Step e: Interactive confirmation
    if interactive:
        # Find the matched investigation for display
        matched_inv = None
        if match_value not in ("new", "generic"):
            for inv in investigations:
                if inv.get("id") == match_value:
                    matched_inv = inv
                    break

        if matched_inv:
            label = matched_inv.get("label", match_value)
            print(f"\nInvestigation context detected:")
            print(f'  → "{label}" (confidence: {confidence:.0%})')
            print(f"  Reason: {reasoning}")
        elif match_value == "new":
            print(f"\nNew investigation suggested:")
            print(f"  Reason: {reasoning}")
        else:
            print(f"\nGeneric/one-off query suggested:")
            print(f"  Reason: {reasoning}")

        print()
        print("[1] Yes, proceed with this selection")
        print("[2] Choose a different investigation")
        print("[3] Create a new investigation")
        print("[4] Generic / one-off query (no investigation context)")

        default_choice = "1"
        if match_value == "new":
            default_choice = "3"
        elif match_value == "generic":
            default_choice = "4"

        try:
            choice = input(f"Choice [{default_choice}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

        if not choice:
            choice = default_choice

        if choice == "1":
            # Accept LLM suggestion
            if match_value in ("new", "generic"):
                return None
            return match_value

        elif choice == "2":
            # List all investigations and let user pick
            print("\nAvailable investigations:")
            for i, inv in enumerate(investigations, 1):
                inv_id = inv.get("id", "unknown")
                label = inv.get("label", inv_id)
                session_count = inv.get("session_count", 0)
                print(f"  [{i}] {inv_id} - {label} (Sessions: {session_count})")

            try:
                pick = input(f"Select investigation [1-{len(investigations)}]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return None

            try:
                idx = int(pick) - 1
                if 0 <= idx < len(investigations):
                    return investigations[idx].get("id")
            except ValueError:
                pass

            print("Invalid selection, using no investigation context.")
            return None

        elif choice == "3":
            # Create new investigation
            try:
                name = input("New investigation name: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return None

            if name:
                return _slugify(name)
            return None

        elif choice == "4":
            # Generic/one-off
            return None

        else:
            # Unknown choice, use default behavior
            if match_value in ("new", "generic"):
                return None
            return match_value

    # Step f: Non-interactive, auto-accept LLM suggestion
    if match_value in ("new", "generic"):
        return None
    return match_value


def create_llm_callable(model: Any) -> Callable[[str], str] | None:
    """Create an LLM callable from a model instance.

    The model is expected to follow the BaseModel protocol with:
    - create_conversation(system_prompt: str, initial_user_message: str) -> Conversation
    - complete(conversation: Conversation) -> ModelTurn

    Args:
        model: A model instance implementing BaseModel protocol

    Returns:
        A callable that takes a prompt string and returns a response string,
        or None if the model doesn't have the required interface.
    """
    if model is None:
        return None

    if not hasattr(model, "create_conversation") or not hasattr(model, "complete"):
        return None

    def llm_call(prompt: str) -> str:
        """Call the LLM with a prompt and return the text response."""
        conversation = model.create_conversation(
            system_prompt="You are a helpful assistant that responds with JSON only.",
            initial_user_message=prompt,
        )
        turn = model.complete(conversation)
        if turn.text is None:
            return ""
        return turn.text.strip()

    return llm_call
