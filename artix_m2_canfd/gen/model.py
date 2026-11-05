"""Data model shared by the generators."""
from dataclasses import dataclass, field

@dataclass
class Pin:
    number: str
    name: str
    net: str | None = None          # None = no connect
    unit: int = 1                   # symbol unit (for multi-unit parts)
    side: str = "L"                 # L or R: which side of the symbol box
    etype: str = "passive"          # KiCad electrical type

@dataclass
class Part:
    ref: str
    value: str
    symbol: str                     # symbol name in the generated library
    footprint: str                  # "lib:name"
    pins: list[Pin]
    mpn: str = ""
    description: str = ""
    sheet: str = "misc"             # schematic sheet name
    place: tuple = (0.0, 0.0, 0.0, "F")   # pcb x, y (mm, board coords), rotation, side
    dnp: bool = False
    zone: str = ""
    owner: str = ""                 # reference of the part this one belongs with (its IC), for grouping
    unit_sheets: dict = field(default_factory=dict)   # unit -> sheet, for units drawn away from the part's sheet

    def sheet_of(self, unit):
        return self.unit_sheets.get(unit, self.sheet)

    def pin(self, number):
        for p in self.pins:
            if p.number == str(number):
                return p
        raise KeyError(f"{self.ref} has no pin {number}")

    def net_of(self, number):
        return self.pin(number).net

    def units(self):
        return sorted({p.unit for p in self.pins})

@dataclass
class Design:
    name: str
    parts: list[Part] = field(default_factory=list)
    sheets: list[str] = field(default_factory=list)   # ordered sheet names
    sheet_titles: dict = field(default_factory=dict)
    owner: str = ""                 # parts added without an explicit owner belong to the last IC declared

    def add(self, part):
        if any(p.ref == part.ref for p in self.parts):
            raise ValueError(f"duplicate reference {part.ref}")
        if not part.owner:
            part.owner = self.owner or part.ref
        self.parts.append(part)
        if part.sheet not in self.sheets:
            self.sheets.append(part.sheet)
        return part

    def nets(self):
        s = set()
        for p in self.parts:
            for pin in p.pins:
                if pin.net:
                    s.add(pin.net)
        return sorted(s)

    def check(self):
        """Single-pin nets are almost always mistakes."""
        count = {}
        for p in self.parts:
            for pin in p.pins:
                if pin.net:
                    count[pin.net] = count.get(pin.net, 0) + 1
        return sorted(n for n, c in count.items() if c < 2)
