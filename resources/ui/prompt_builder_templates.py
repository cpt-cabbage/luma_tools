"""
Template engine for Prompt Builder.

Handles variable substitution and weight formatting for different prompt formats.
"""

import re
from typing import Dict, List, Optional
from prompt_builder_models import PromptCategory, PromptBuilderState, get_category_by_id, get_option_by_id


# Built-in template definitions
BUILTIN_TEMPLATES = {
    "Natural Language": "{description}. Shot with {camera_type} using {lens}, {style} style. {framerate}, {shutter_speed}, {motion_speed}. {depth_of_field}. {movement}. {post_filters}.",
    "Keyword List": "{description}, {camera_type}, {lens}, {aberration}, {camera_filter}, {special_filter}, {style}, {framerate}, {shutter_speed}, {motion_speed}, {depth_of_field}, {movement}, {post_filters}, {visual_effects}",
    "Weighted Tags": "{description:weighted}, {camera_type:weighted}, {lens:weighted}, {style:weighted}, {framerate:weighted}, {shutter_speed:weighted}, {motion_speed:weighted}, {depth_of_field:weighted}, {movement:weighted}, {post_filters:weighted}, {visual_effects:weighted}",
    "ComfyUI Format": "({description}:1.0), {camera_type:weighted}, {lens:weighted}, {style:weighted}, {framerate:weighted}, {shutter_speed:weighted}, {motion_speed:weighted}, {depth_of_field:weighted}, {movement:weighted}, {post_filters:weighted}, {visual_effects:weighted}",
    "Simple List": "{description}\n{camera_type}\n{lens}\n{aberration}\n{camera_filter}\n{special_filter}\n{style}\n{framerate}\n{shutter_speed}\n{motion_speed}\n{depth_of_field}\n{movement}\n{post_filters}\n{visual_effects}",
    "Technical JSON Format": "{description}. Camera: {camera_type} with {lens} ({aberration}). Filters: {camera_filter}, {special_filter}. Style: {style}. Technical: {framerate}, {shutter_speed}, {motion_speed}, {depth_of_field}. Movement: {movement}. Post: {post_filters}.",
}


def format_weighted_auto1111(text: str, weight: float) -> str:
    """Format text with weight in Automatic1111 style: (text:weight)"""
    if weight == 1.0:
        return text
    return f"({text}:{weight:.2f})"


def format_weighted_novel(text: str, weight: float) -> str:
    """Format text with weight in NovelAI style: {text} for 1.05, {{text}} for 1.1"""
    if weight == 1.0:
        return text
    elif weight <= 1.05:
        return f"{{{text}}}"
    elif weight <= 1.15:
        return f"{{{{{text}}}}}"
    else:
        # Fall back to parentheses for higher weights
        return f"({text}:{weight:.2f})"


def format_option_list(
    option_labels: List[str],
    weights: Dict[str, float],
    option_ids: List[str],
    weighted: bool = False
) -> str:
    """
    Format a list of options as comma-separated string.

    Args:
        option_labels: Human-readable labels
        weights: Option ID to weight mapping
        option_ids: Option IDs in same order as labels
        weighted: Whether to apply weight formatting
    """
    if not option_labels:
        return ""

    if weighted:
        formatted = []
        for label, opt_id in zip(option_labels, option_ids):
            weight = weights.get(opt_id, 1.0)
            formatted.append(format_weighted_auto1111(label, weight))
        return ", ".join(formatted)
    else:
        return ", ".join(option_labels)


class TemplateEngine:
    """Handles template variable substitution and formatting"""

    def __init__(self, categories: List[PromptCategory]):
        self.categories = categories

    def render(
        self,
        template: str,
        state: PromptBuilderState,
        is_negative: bool = False
    ) -> str:
        """
        Render template with current state.

        Args:
            template: Template string with {variables}
            state: Current builder state
            is_negative: Whether to use negative selections

        Returns:
            Formatted prompt string
        """
        # Choose positive or negative selections
        selections = state.negative_selections if is_negative else state.positive_selections
        weights = state.negative_weights if is_negative else state.positive_weights

        # Build variable context
        context = {}

        # Add description
        context['description'] = state.description.strip()

        # Add each category
        for category in self.categories:
            cat_id = category.id
            selected_ids = selections.get(cat_id, [])

            # Get labels for selected options
            labels = []
            for opt_id in selected_ids:
                option = get_option_by_id(category, opt_id)
                if option:
                    labels.append(option.label)

            # Plain format (no weights)
            context[cat_id] = ", ".join(labels) if labels else ""

            # Weighted format
            weighted_text = format_option_list(labels, weights, selected_ids, weighted=True)
            context[f"{cat_id}:weighted"] = weighted_text

            # Novel AI format
            novel_labels = []
            for label, opt_id in zip(labels, selected_ids):
                weight = weights.get(opt_id, 1.0)
                novel_labels.append(format_weighted_novel(label, weight))
            context[f"{cat_id}:weighted_novel"] = ", ".join(novel_labels) if novel_labels else ""

        # Add weighted description variants
        context['description:weighted'] = format_weighted_auto1111(state.description.strip(), 1.0)

        # Perform substitution
        result = template
        for key, value in context.items():
            result = result.replace(f"{{{key}}}", value)

        # Clean up: remove empty clauses
        result = self._clean_empty_clauses(result)

        return result.strip()

    def _clean_empty_clauses(self, text: str) -> str:
        """Remove empty clauses like ', , ' or '. .' """
        # Remove multiple commas/periods with only whitespace between
        text = re.sub(r',\s*,+', ',', text)
        text = re.sub(r'\.\s*\.+', '.', text)

        # Remove leading/trailing commas and periods
        text = re.sub(r'^[,.\s]+', '', text)
        text = re.sub(r'[,.\s]+$', '', text)

        # Remove empty parentheses
        text = re.sub(r'\(\s*\)', '', text)

        # Clean up multiple spaces
        text = re.sub(r'\s+', ' ', text)

        # Remove clauses that are just punctuation
        text = re.sub(r'[,;]\s*[,;]', ',', text)

        return text

    def get_available_variables(self) -> List[str]:
        """Get list of all available template variables"""
        variables = ['description', 'description:weighted']

        for category in self.categories:
            cat_id = category.id
            variables.extend([
                cat_id,
                f"{cat_id}:weighted",
                f"{cat_id}:weighted_novel"
            ])

        return variables


def get_builtin_templates() -> Dict[str, str]:
    """Get a copy of built-in templates"""
    return BUILTIN_TEMPLATES.copy()


def get_template_help_text() -> str:
    """Get help text explaining template syntax"""
    return """
Template Syntax:

Camera Variables:
  {description}       - Free text description
  {camera_type}       - Camera body type (Digital Cinema, DSLR, etc.)
  {lens}              - Lens type (Prime, Anamorphic, Wide Angle, etc.)
  {aberration}        - Lens aberration setting
  {camera_filter}     - Physical camera filter (ND, Polarizing, etc.)
  {special_filter}    - Special effects filter (Star, Fog, etc.)
  {movement}          - Camera movement (Pan, Dolly, Steadicam, etc.)

Style Variables:
  {style}             - Film style (Cinematic, Noir, Documentary, etc.)

Technical Variables:
  {framerate}         - Frame rate (24fps, 60fps, etc.)
  {shutter_speed}     - Shutter speed (1/50, 1/100, etc.)
  {motion_speed}      - Motion speed (Normal, Slow Motion, etc.)
  {depth_of_field}    - Depth of field (Shallow, Deep, etc.)

Post-Processing Variables:
  {post_filters}      - Post-processing filters (Film Grain, Bloom, etc.)
  {visual_effects}    - Visual effects (Motion Blur, Rack Focus, etc.)

Weight Formats:
  {camera_type:weighted}       - Automatic1111 style: (Digital Cinema Camera:1.2)
  {lens:weighted_novel}        - NovelAI style: {Anamorphic Lens} or {{Anamorphic Lens}}

Example Templates:
  Natural: "{description}. Shot with {camera_type} using {lens}, {style} style."
  Weighted: "({description}:1.0), {camera_type:weighted}, {lens:weighted}, {style:weighted}"
  Keywords: "{description}, camera:{camera_type}, lens:{lens}, style:{style}"
    """.strip()
