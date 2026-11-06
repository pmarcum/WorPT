"""The data a WorPT proposal holds (what the dashboard edits and the server stores)."""
from dataclasses import dataclass, field
from .effort import Member, Assignment, Item          # noqa: F401  (re-exported for callers)


@dataclass
class Person(Member):
    """A team member on one proposal. `role` keeps WorPT's short form, e.g. PI, Sci-PI, co-I(1), coll(2), gst(1)."""
    last: str = ''
    first: str = ''
    middle: str = ''
    prefix: str = ''          # e.g. Dr.
    suffix: str = ''          # e.g. III
    institution: str = ''
    position: str = ''
    bio_summary: str = ''     # role/background narrative (team summaries table)
    task_summary: str = ''    # short HST-style role text (HST table)
    trips: list = field(default_factory=list)   # per year: [domestic trips, international trips]


@dataclass
class TravelCosts:
    """Per-trip cost assumptions: each of airfare, perdiem, conference, ground is
    [domestic, international, yearly increase as a fraction]; days is [domestic, international]."""
    airfare: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    perdiem: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    conference: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    ground: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    days: list = field(default_factory=lambda: [0.0, 0.0])


@dataclass
class NonlaborItem:
    item: str                 # LaTeX allowed, e.g. "Materials \\& Supplies"
    amounts: list             # dollars per year


@dataclass
class Proposal:
    title: str
    program: str              # funding program, e.g. "NASA/ADAP2031"; "HST" switches team summaries to full role names
    n_years: int
    members: list             # [Person]
    goals: list               # [Item] goal > task > subtask
    nonlabor: list = field(default_factory=list)       # [NonlaborItem]
    travel: TravelCosts = field(default_factory=TravelCosts)
    latex_subdir: str = 'do_NOT_manually_edit'
    rounding: str = 'nearest'
    weeks_per_fte: float = 52
