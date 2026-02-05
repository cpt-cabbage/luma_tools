"""
Data models for the Prompt Builder feature.

Defines the structure for categories, options, and builder state.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional


@dataclass
class PromptOption:
    """Single selectable option within a category"""
    id: str              # Unique ID (e.g., "camera_35mm")
    label: str           # Display name ("35mm")
    description: str     # Tooltip/help text
    weight: float = 1.0  # Default weight (1.0 = neutral)

    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'PromptOption':
        """Deserialize from dictionary"""
        return cls(**data)


@dataclass
class PromptCategory:
    """Category of related options"""
    id: str                          # "camera", "style", etc.
    label: str                       # "Camera Type"
    options: List[PromptOption]
    multi_select: bool = False       # Allow multiple selections
    allow_weights: bool = True       # Show weight spinboxes

    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            'id': self.id,
            'label': self.label,
            'options': [opt.to_dict() for opt in self.options],
            'multi_select': self.multi_select,
            'allow_weights': self.allow_weights
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'PromptCategory':
        """Deserialize from dictionary"""
        options = [PromptOption.from_dict(opt) for opt in data['options']]
        return cls(
            id=data['id'],
            label=data['label'],
            options=options,
            multi_select=data.get('multi_select', False),
            allow_weights=data.get('allow_weights', True)
        )


@dataclass
class PromptBuilderState:
    """Current selections in the builder"""
    positive_selections: Dict[str, List[str]] = field(default_factory=dict)  # category_id -> [option_id, ...]
    positive_weights: Dict[str, float] = field(default_factory=dict)         # option_id -> weight
    negative_selections: Dict[str, List[str]] = field(default_factory=dict)  # Same for negative
    negative_weights: Dict[str, float] = field(default_factory=dict)
    description: str = ""                                                     # Free text description
    output_template: str = "Natural Language"                                 # Template name

    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'PromptBuilderState':
        """Deserialize from dictionary"""
        return cls(**data)

    def to_json_output(self, categories: List[PromptCategory], negative_prompt: str = "") -> dict:
        """
        Export state as structured JSON matching the output format.

        Args:
            categories: List of all available categories
            negative_prompt: Generated negative prompt text

        Returns:
            Dictionary with description, negativePrompt, and settings structure
        """
        # Helper to get selected option label
        def get_selected_label(category_id: str, default: str = "None") -> str:
            selected_ids = self.positive_selections.get(category_id, [])
            if not selected_ids:
                return default

            category = get_category_by_id(categories, category_id)
            if not category:
                return default

            option = get_option_by_id(category, selected_ids[0])
            return option.label if option else default

        return {
            "description": self.description.strip(),
            "negativePrompt": negative_prompt,
            "settings": {
                "camera": {
                    "type": get_selected_label("camera_type", "Digital Cinema Camera"),
                    "lens": get_selected_label("lens", "Prime Lens"),
                    "aberration": get_selected_label("aberration", "Clean, No Aberration"),
                    "filter": get_selected_label("camera_filter", "None"),
                    "specialFilter": get_selected_label("special_filter", "None"),
                    "cameraMovement": get_selected_label("movement", "Fixed camera without camera movement")
                },
                "style": {
                    "filmStyle": get_selected_label("style", "Cinematic (Hollywood)")
                },
                "technical": {
                    "framerate": get_selected_label("framerate", "24fps (Standard Cinematic)"),
                    "shutterSpeed": get_selected_label("shutter_speed", "1/50 (180-degree rule for 24fps)"),
                    "motion": get_selected_label("motion_speed", "Normal Motion"),
                    "depthOfField": get_selected_label("depth_of_field", "Shallow Depth of Field (Background blurry)")
                }
            }
        }


# Default Veo-inspired categories
DEFAULT_CATEGORIES = [
    # Camera settings group
    PromptCategory(
        id="camera_type",
        label="Camera Type",
        options=[
            PromptOption("cam_digital_cinema", "Digital Cinema Camera", "High-end digital cinema camera"),
            PromptOption("cam_dslr", "DSLR Camera", "Consumer/prosumer digital camera"),
            PromptOption("cam_mirrorless", "Mirrorless Camera", "Modern mirrorless camera system"),
            PromptOption("cam_film_35mm", "35mm Film Camera", "Traditional 35mm film camera"),
            PromptOption("cam_film_16mm", "16mm Film Camera", "Documentary-style 16mm film"),
            PromptOption("cam_imax", "IMAX Camera", "Large format IMAX"),
            PromptOption("cam_action", "Action Camera", "GoPro-style wide angle action cam"),
            PromptOption("cam_smartphone", "Smartphone Camera", "Mobile phone camera"),
        ],
        multi_select=False,
        allow_weights=False
    ),
    PromptCategory(
        id="lens",
        label="Lens Type",
        options=[
            PromptOption("lens_prime", "Prime Lens", "Fixed focal length lens"),
            PromptOption("lens_zoom", "Zoom Lens", "Variable focal length lens"),
            PromptOption("lens_anamorphic", "Anamorphic Lens (Wide aspect ratio, Oval bokeh)", "Cinematic widescreen with oval bokeh"),
            PromptOption("lens_wide", "Wide Angle Lens (Expansive view)", "Broad field of view"),
            PromptOption("lens_telephoto", "Telephoto Lens (Compressed perspective)", "Long focal length, compressed depth"),
            PromptOption("lens_macro", "Macro Lens (Extreme close-up)", "Specialized for close-up detail"),
            PromptOption("lens_fisheye", "Fisheye Lens (Ultra-wide, Distorted)", "Extreme wide angle with distortion"),
            PromptOption("lens_tilt_shift", "Tilt-Shift Lens (Miniature effect)", "Plane of focus manipulation"),
        ],
        multi_select=False,
        allow_weights=False
    ),
    PromptCategory(
        id="aberration",
        label="Lens Aberration",
        options=[
            PromptOption("aberr_none", "Clean, No Aberration", "Optically perfect, no distortion"),
            PromptOption("aberr_subtle", "Subtle Chromatic Aberration", "Slight color fringing at edges"),
            PromptOption("aberr_moderate", "Moderate Chromatic Aberration", "Noticeable color separation"),
            PromptOption("aberr_strong", "Strong Chromatic Aberration", "Heavy color fringing and distortion"),
            PromptOption("aberr_vintage", "Vintage Lens Aberration", "Period-accurate optical imperfections"),
        ],
        multi_select=False,
        allow_weights=False
    ),
    PromptCategory(
        id="camera_filter",
        label="Camera Filter",
        options=[
            PromptOption("filter_none", "None", "No filter"),
            PromptOption("filter_nd", "ND Filter (Neutral Density)", "Reduces light without color shift"),
            PromptOption("filter_polarizing", "Polarizing Filter", "Reduces reflections and glare"),
            PromptOption("filter_uv", "UV Filter", "Blocks ultraviolet light"),
            PromptOption("filter_grad_nd", "Graduated ND Filter", "Darkens sky, balances exposure"),
            PromptOption("filter_diffusion", "Diffusion Filter", "Softens highlights and skin tones"),
        ],
        multi_select=False,
        allow_weights=False
    ),
    PromptCategory(
        id="special_filter",
        label="Special Filter",
        options=[
            PromptOption("special_none", "None", "No special filter"),
            PromptOption("special_star", "Star Filter", "Creates star-shaped light rays"),
            PromptOption("special_soft_focus", "Soft Focus Filter", "Dreamy, ethereal look"),
            PromptOption("special_fog", "Fog Filter", "Adds atmospheric haze"),
            PromptOption("special_color_gel", "Color Gel Filter", "Colored filter for creative effects"),
            PromptOption("special_infrared", "Infrared Filter", "False-color infrared look"),
        ],
        multi_select=False,
        allow_weights=False
    ),
    PromptCategory(
        id="movement",
        label="Camera Movement",
        options=[
            PromptOption("move_static", "Fixed camera without camera movement", "Locked-off, no camera movement"),
            PromptOption("move_pan", "Pan (Horizontal rotation)", "Horizontal camera rotation"),
            PromptOption("move_tilt", "Tilt (Vertical rotation)", "Vertical camera rotation"),
            PromptOption("move_dolly", "Dolly In/Out (Moving toward/away)", "Camera moves toward/away from subject"),
            PromptOption("move_tracking", "Tracking Shot (Following subject)", "Camera follows subject laterally"),
            PromptOption("move_crane", "Crane Shot (Vertical movement)", "Vertical camera movement"),
            PromptOption("move_handheld", "Handheld (Documentary style)", "Shaky, documentary-style movement"),
            PromptOption("move_steadicam", "Steadicam (Smooth floating)", "Smooth, floating movement"),
            PromptOption("move_orbit", "Orbit (Circling subject)", "Camera circles around subject"),
            PromptOption("move_zoom", "Zoom (Lens focal length change)", "Lens focal length change"),
        ],
        multi_select=False,
        allow_weights=False
    ),

    # Style group
    PromptCategory(
        id="style",
        label="Film Style",
        options=[
            PromptOption("style_cinematic", "Cinematic (Hollywood)", "Hollywood blockbuster style"),
            PromptOption("style_vintage", "Vintage (Retro film aesthetic)", "Retro film aesthetic with grain"),
            PromptOption("style_noir", "Film Noir (High contrast B&W)", "High contrast black & white"),
            PromptOption("style_anime", "Anime (Japanese animation)", "Japanese animation style"),
            PromptOption("style_documentary", "Documentary (Natural realism)", "Natural, unfiltered realism"),
            PromptOption("style_music_video", "Music Video (Stylized)", "Stylized, fast-paced editing"),
            PromptOption("style_cyberpunk", "Cyberpunk (Neon dystopia)", "Neon-lit futuristic dystopia"),
            PromptOption("style_fantasy", "Fantasy (Magical atmosphere)", "Magical, otherworldly atmosphere"),
        ],
        multi_select=False,
        allow_weights=False
    ),

    # Technical settings group
    PromptCategory(
        id="framerate",
        label="Frame Rate",
        options=[
            PromptOption("fps_24", "24fps (Standard Cinematic)", "Standard cinema frame rate"),
            PromptOption("fps_25", "25fps (PAL video standard)", "European video standard"),
            PromptOption("fps_30", "30fps (NTSC video standard)", "American video standard"),
            PromptOption("fps_48", "48fps (High frame rate cinema)", "Smooth cinematic motion"),
            PromptOption("fps_60", "60fps (Smooth video)", "Standard high frame rate video"),
            PromptOption("fps_120", "120fps (High-speed capture)", "High-speed for slow motion"),
            PromptOption("fps_240", "240fps (Ultra high-speed)", "Ultra high-speed for extreme slow motion"),
        ],
        multi_select=False,
        allow_weights=False
    ),
    PromptCategory(
        id="shutter_speed",
        label="Shutter Speed",
        options=[
            PromptOption("shutter_1_50", "1/50 (180-degree rule for 24fps)", "Natural motion blur at 24fps"),
            PromptOption("shutter_1_60", "1/60 (180-degree rule for 30fps)", "Natural motion blur at 30fps"),
            PromptOption("shutter_1_100", "1/100 (Moderate motion blur)", "Slightly reduced motion blur"),
            PromptOption("shutter_1_125", "1/125 (180-degree rule for 60fps)", "Natural motion blur at 60fps"),
            PromptOption("shutter_1_200", "1/200 (Reduced motion blur)", "Sharper motion, less blur"),
            PromptOption("shutter_1_500", "1/500 (Minimal motion blur)", "Very sharp motion capture"),
            PromptOption("shutter_1_1000", "1/1000 (Freeze motion)", "Frozen action, no blur"),
        ],
        multi_select=False,
        allow_weights=False
    ),
    PromptCategory(
        id="motion_speed",
        label="Motion Speed",
        options=[
            PromptOption("motion_normal", "Normal Motion", "Real-time playback speed"),
            PromptOption("motion_slow", "Slow Motion (Time-stretched)", "Slowed down for dramatic effect"),
            PromptOption("motion_fast", "Fast Motion (Time-lapse)", "Sped up time passage"),
            PromptOption("motion_variable", "Variable Speed (Ramping)", "Speed changes within shot"),
        ],
        multi_select=False,
        allow_weights=False
    ),
    PromptCategory(
        id="depth_of_field",
        label="Depth of Field",
        options=[
            PromptOption("dof_shallow", "Shallow Depth of Field (Background blurry)", "Subject sharp, background soft/blurred"),
            PromptOption("dof_deep", "Deep Depth of Field (Everything sharp)", "Everything in focus, front to back"),
            PromptOption("dof_moderate", "Moderate Depth of Field", "Balanced focus range"),
            PromptOption("dof_selective", "Selective Focus (Single plane sharp)", "Very thin plane of focus"),
        ],
        multi_select=False,
        allow_weights=False
    ),

    # Post-processing effects (keep for prompt building)
    PromptCategory(
        id="post_filters",
        label="Post-Processing Filters",
        options=[
            PromptOption("filter_grainy", "Film Grain", "Visible film grain texture"),
            PromptOption("filter_bloom", "Bloom", "Glowing highlights and soft edges"),
            PromptOption("filter_vignette", "Vignette", "Darkened edges, centered focus"),
            PromptOption("filter_chromatic_post", "Chromatic Aberration (Post)", "Color fringing added in post"),
            PromptOption("filter_lens_flare", "Lens Flare", "Light artifacts and streaks"),
            PromptOption("filter_film_burn", "Film Burn", "Overexposed vintage film effect"),
            PromptOption("filter_sepia", "Sepia Tone", "Warm brownish vintage coloring"),
            PromptOption("filter_color_grade", "Color Grading", "Stylized color palette"),
        ],
        multi_select=True,
        allow_weights=True
    ),
    PromptCategory(
        id="visual_effects",
        label="Visual Effects",
        options=[
            PromptOption("fx_motion_blur", "Motion Blur", "Blurred movement trails"),
            PromptOption("fx_rack_focus", "Rack Focus", "Focus shift between subjects"),
            PromptOption("fx_dutch_angle", "Dutch Angle", "Tilted camera angle"),
            PromptOption("fx_lens_distortion", "Lens Distortion", "Warped perspective"),
            PromptOption("fx_split_screen", "Split Screen", "Multiple views simultaneously"),
        ],
        multi_select=True,
        allow_weights=True
    ),
]


def get_default_categories() -> List[PromptCategory]:
    """Get a copy of the default categories"""
    import copy
    return copy.deepcopy(DEFAULT_CATEGORIES)


def get_category_by_id(categories: List[PromptCategory], category_id: str) -> Optional[PromptCategory]:
    """Find category by ID"""
    for cat in categories:
        if cat.id == category_id:
            return cat
    return None


def get_option_by_id(category: PromptCategory, option_id: str) -> Optional[PromptOption]:
    """Find option by ID within a category"""
    for opt in category.options:
        if opt.id == option_id:
            return opt
    return None
