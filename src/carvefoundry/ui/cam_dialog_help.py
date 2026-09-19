"""Single source of truth for the CAM form's in-context help text.

Pure data: no Qt imports or CAM side effects. Each form field is backed by
one explanatory entry shown by its adjacent ? control.
"""
from __future__ import annotations


def cam_generation_help() -> dict[str, tuple[str, str]]:
    """Return field key → accessible title and full explanation."""
    return {
        "source_summary": (
            "Objects",
            (
                "Generate Toolpaths works from the project, not the current "
                "viewport selection. Every design object containing mesh "
                "geometry is included ONLY if visible. Surface / Face is "
                "the exception: it can run from the stock even when the "
                "project has no geometry. Hide a model in Layers to exclude "
                "it; selecting or isolating does not change the source set."
            ),
        ),
        "operation": (
            "Toolpath",
            (
                "Choose the machining operation to generate.\n\n"
                "Profile — follows projected model boundaries at one or more "
                "depths. The 2D Cut Type controls whether the cutter runs on, "
                "inside, outside, or clears the region.\n\n"
                "Silhouette — builds one project-wide outside envelope from "
                "all design geometry. Internal holes are intentionally ignored.\n\n"
                "Pocket — clears the interior of projected closed regions.\n\n"
                "Surface / Face — faces the stock top and can run without any "
                "design objects.\n\n"
                "V-Carve — follows vector/detail geometry with a V-bit or "
                "engraving cone. A valid included cutter angle is required.\n\n"
                "Engrave — traces projected linework/contours with the selected "
                "cutter and supports the 2D Cut Type choices.\n\n"
                "Drill Features — finds drill-like circular projected features "
                "and drills their centers.\n\n"
                "Center Drill — drills the centroid of each disconnected "
                "projected region, whether or not that region is circular.\n\n"
                "3D Rough — removes bulk material from the 3D model using the "
                "selected cutter geometry and roughing strategy.\n\n"
                "3D Finish — cutter-compensated finishing over the model "
                "surface; Detail and Direction control raster density/layout.\n\n"
                "Height Map — uses CarveFoundry's high-detail 3D surface "
                "finishing engine on model geometry. It is not a separate "
                "bitmap height-map importer.\n\n"
                "3D Rest — stock-aware cleanup after preceding generated cutter stages.\n"
                "Simulates remaining stock, then machines only cutter-contact\n"
                "samples where material remains above your tolerance.\n\n"
                "3D Waterline — creates constant-Z contour passes around the "
                "3D model at successive levels."
            ),
        ),
        "stock": (
            "Stock",
            (
                "Shows the active stock width × height × thickness in "
                "millimeters. Toolpaths, Safe Z, cut depth, cutouts, and stock "
                "surfacing are evaluated against this stock definition. Change "
                "the stock from Stock Setup before opening this dialog if these "
                "dimensions are wrong."
            ),
        ),
        "cutter": (
            "Selected cutter",
            (
                "Select the physical cutter that will run this operation. "
                "CarveFoundry compensates generated geometry for the selected "
                "tool profile rather than assuming every tool is a ball nose. "
                "Diameter, tool type, included angle, and tip diameter can all "
                "change the resulting path. V-Carve requires a V-bit or "
                "engraving cone with a valid included angle. The tool must "
                "match the cutter actually installed in the machine."
            ),
        ),
        "cutter_details": (
            "Cutter geometry",
            (
                "Read-only summary of the selected cutter definition: tool "
                "type, diameter, and angle/tip diameter when applicable. Use "
                "this line as a final sanity check before generating. Incorrect "
                "cutter geometry produces incorrect cutter compensation even "
                "when every other CAM setting is correct."
            ),
        ),
        "cut_type": (
            "2D cut type",
            (
                "Controls how 2D Profile, Pocket, and Engrave operations relate "
                "the cutter centerline to projected geometry.\n\n"
                "Auto — use the operation's normal/default behavior.\n"
                "Pocket — clear the interior region instead of tracing only a "
                "boundary.\n"
                "On Path — place the cutter centerline directly on the "
                "projected contour.\n"
                "Outside — offset the cutter centerline outward by its radius "
                "so the model boundary is preserved on the inside.\n"
                "Inside — offset inward by the cutter radius so the outside "
                "boundary is preserved."
            ),
        ),
        "3d_style": (
            "3D style",
            (
                "Chooses the area and finishing behavior for 3D operations.\n\n"
                "Model Boundary Relief — constrain the relief to the projected "
                "model boundary.\n"
                "Rectangle Relief — machine the rectangular model/work "
                "envelope rather than only the projected silhouette.\n"
                "Full Depth Cutout — finish the 3D model and also generate an "
                "outside profile through the stock so the part can be freed. "
                "Holding tabs become available for this mode."
            ),
        ),
        "direction": (
            "Direction",
            (
                "Controls the pattern/orientation used where an operation "
                "supports directional passes.\n\n"
                "Smart Serpentine — prioritizes a continuous back-and-forth "
                "path with minimal air cutting and minimal Z lifts.\n"
                "Offset — uses nested/offset contours where supported.\n"
                "Raster X — long cutting runs parallel to X.\n"
                "Raster Y — long cutting runs parallel to Y.\n"
                "Raster 45° — diagonal raster at 45 degrees.\n"
                "Raster 135° — opposite diagonal raster at 135 degrees.\n\n"
                "The most efficient direction depends on model shape, grain, "
                "clamping, cutter, and the surface detail you are trying to "
                "preserve."
            ),
        ),
        "detail": (
            "3D / V-Carve detail",
            (
                "Controls path density for 3D finishing and the supported "
                "V-Carve detail behavior. Higher values create denser sampling "
                "and smaller finishing stepover, improving fine detail and "
                "surface smoothness at the cost of more G-code and longer run "
                "time. Lower values generate fewer passes and run faster. "
                "Changing Detail does not make a cutter physically capable of "
                "reaching features smaller than its geometry."
            ),
        ),
        "pocket_stepover": (
            "2D pocket stepover",
            (
                "Sets lateral spacing between adjacent pocket/surface passes as "
                "a percentage of cutter diameter. For example, 40% means the "
                "next pass center is approximately 0.40 cutter diameters away. "
                "Lower percentages overlap more, usually leaving a smoother "
                "surface but increasing run time. Higher percentages remove "
                "material faster but can leave larger scallops or uncut areas "
                "with unsuitable tool/geometry combinations."
            ),
        ),
        "padding": (
            "Path / relief padding",
            (
                "Adds lateral margin around path or relief boundaries where the "
                "chosen operation supports padding. 0 mm uses the calculated "
                "boundary directly. Positive padding expands the machining "
                "envelope, which can be useful for clearing beyond an edge or "
                "giving a finishing cutter room to reach the model boundary. "
                "Verify clamp and stock-edge clearance before increasing it."
            ),
        ),
        "cut_depth": (
            "Overall cut depth",
            (
                "Maximum requested machining depth below stock Z0. A value of "
                "0 tells CarveFoundry to derive depth from the model/operation "
                "instead of forcing an override. A positive value overrides the "
                "normal model depth for operations that use this setting. The "
                "requested depth is also checked against Usable Bit Length when "
                "that limit is enabled."
            ),
        ),
        "stepdown": (
            "Depth per pass",
            (
                "Maximum axial depth removed in one Z level/pass. Smaller "
                "stepdowns reduce cutter load and are safer for small tools, "
                "hard material, or less rigid machines, but create more passes. "
                "Larger values reduce pass count but increase cutting load. "
                "CarveFoundry divides the requested total depth into passes that "
                "do not exceed this value."
            ),
        ),
        "bit_length": (
            "Usable bit length",
            (
                "Optional depth-safety limit for the cutter. 0 disables this "
                "check. A positive value represents the cutting length you are "
                "willing to use below the tool/holder and blocks a requested "
                "overall depth that exceeds it. This is a validation aid, not a "
                "complete holder/clamp collision simulation."
            ),
        ),
        "safe_z": (
            "Safe Z",
            (
                "Full-retract clearance above stock Z0, in millimeters. "
                "CarveFoundry uses this for initial positioning, final retracts, "
                "Full Retract linking, and transitions that cannot be proven "
                "safe at a lower height. Keep it high enough to clear the stock, "
                "fixtures, fences, and clamps that the tool may cross. A larger "
                "value is safer but increases non-cutting travel time."
            ),
        ),
        "feed": (
            "Cut feed",
            (
                "XY/3D cutting feed rate in millimeters per minute for normal "
                "cutting moves. It must be appropriate for cutter diameter, "
                "flute geometry, spindle/router speed, material, depth per pass, "
                "and machine rigidity. This field does not automatically "
                "guarantee a safe chip load."
            ),
        ),
        "plunge": (
            "Plunge feed",
            (
                "Feed rate used when moving downward into material. Plunge "
                "moves usually need to be slower than lateral cutting because "
                "many cutters evacuate chips less effectively at the center. "
                "Ramp entries can reduce the amount of straight-down plunging "
                "for operations that support them."
            ),
        ),
        "entry": (
            "Entry",
            (
                "Controls how supported 2D/2.5D operations enter each cutting "
                "depth.\n\n"
                "Plunge — descend vertically at the Plunge Feed.\n"
                "Ramp 5° — enter gradually along a shallow 5-degree ramp.\n"
                "Ramp 20° — use a steeper 20-degree ramp requiring less XY "
                "distance.\n"
                "Custom Ramp — use the angle entered in Custom Ramp.\n\n"
                "Shallower ramps generally reduce axial shock but require more "
                "room. The control is disabled for operations whose current "
                "generator does not use entry ramps."
            ),
        ),
        "ramp_angle": (
            "Custom ramp",
            (
                "Ramp angle used only when Entry is Custom Ramp. Small angles "
                "produce a long, gentle entry; large angles are shorter and "
                "closer to a plunge. The valid range stays below 90 degrees. "
                "Make sure the model/pocket has enough travel length for the "
                "chosen angle and depth."
            ),
        ),
        "milling": (
            "Milling direction",
            (
                "Controls contour direction for operations that support climb "
                "or conventional milling.\n\n"
                "Default — let the operation choose its normal direction.\n"
                "Climb (CCW) — request CarveFoundry's climb-milling contour "
                "direction.\n"
                "Conventional (CW) — request the opposite conventional "
                "direction.\n\n"
                "Actual cutting forces also depend on whether a contour is "
                "inside or outside. Use the direction appropriate for your "
                "machine, workholding, cutter, and material."
            ),
        ),
        "linking": (
            "Path linking",
            (
                "Controls how CarveFoundry moves between separate cutting "
                "segments.\n\n"
                "Smart Min-Lift — preferred fast mode. Keep the cutter at "
                "cutting depth when a transition is verified safe; otherwise "
                "use a small local clearance, reserving full Safe Z for "
                "disconnected/unsafe travel and initial/final moves.\n"
                "Local Lift — use short local-clearance transitions instead of "
                "direct cutting-depth links where possible.\n"
                "Full Retract — retract to Safe Z between separate path "
                "segments. This is slowest but most conservative."
            ),
        ),
        "local_clearance": (
            "Local lift clearance",
            (
                "Extra Z clearance used by Local Lift and by Smart Min-Lift "
                "when a direct cutting-depth connection is not safe. "
                "CarveFoundry raises the cutter above the highest required "
                "surface along a connected transition corridor by this amount, "
                "without exceeding full Safe Z. Increase it for more margin; "
                "decrease it to reduce air time only when setup accuracy allows."
            ),
        ),
        "link_tolerance": (
            "Direct-link tolerance",
            (
                "3D-only tolerance used by Smart Min-Lift when deciding whether "
                "two raster runs may be connected directly at cutting depth. "
                "The contact-map samples along the corridor must stay within "
                "this allowed surface/clearance difference. A smaller value is "
                "more conservative and causes more local lifts; a larger value "
                "permits more direct links. 0 requires the strictest match."
            ),
        ),
        "tabs_enabled": (
            "Use holding tabs",
            (
                "Keep small bridges of material during through-cut profiles so "
                "the part remains attached to the surrounding stock. Tabs are "
                "available for Profile, Silhouette, and 3D Finish when Full "
                "Depth Cutout is selected. Turn them off only when another "
                "workholding method safely prevents the finished part from "
                "moving into the cutter."
            ),
        ),
        "tab_height": (
            "Tab height",
            (
                "Amount of material left vertically in each holding tab. More "
                "height makes tabs stronger but requires more cleanup after the "
                "cut. Too little height can allow the part to break free before "
                "the profile completes. This value is only used when holding "
                "tabs are enabled."
            ),
        ),
        "tab_width": (
            "Tab width",
            (
                "Length of each holding bridge measured along the cut path. "
                "Wider tabs hold more strongly but take more effort to remove "
                "and clean up. This value is only used when holding tabs are "
                "enabled."
            ),
        ),
        "tab_count": (
            "Tab count",
            (
                "Number of holding tabs distributed around the cutout/profile. "
                "More tabs improve restraint on large or flexible parts but add "
                "cleanup. Use enough tabs to resist cutting forces without "
                "placing them where they interfere with important finished "
                "details."
            ),
        ),
        "readiness": (
            "Generation readiness",
            (
                "Live preflight checklist for the current dialog settings. "
                "Green checks are requirements that currently pass. Red items "
                "must be corrected before Generate Toolpaths is enabled. The "
                "checklist verifies basic geometry, cutter compatibility, stock "
                "dimensions, feeds/depth settings, usable bit length, and tabs "
                "when applicable; it does not replace a physical setup and "
                "collision check at the machine."
            ),
        ),
    }
